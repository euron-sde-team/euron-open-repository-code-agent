// Package ratelimit implements token-bucket rate limiting.
package ratelimit

import (
	"time"

	"example.com/ratelimit/store"
)

// DefaultBurst is the bucket size when a Limiter is created without one.
const DefaultBurst = 10

// Limiter allows Rate events per second per key, with bursts up to Burst.
type Limiter struct {
	Rate  float64
	Burst int
	store store.Store
	now   func() time.Time
}

// New returns a Limiter backed by the given store.
func New(rate float64, burst int, s store.Store) *Limiter {
	if burst <= 0 {
		burst = DefaultBurst
	}
	return &Limiter{Rate: rate, Burst: burst, store: s, now: time.Now}
}

// Allow reports whether one event for key may happen now, and records it if so.
func (l *Limiter) Allow(key string) bool {
	return l.AllowN(key, 1)
}

// AllowN reports whether n events for key may happen now.
func (l *Limiter) AllowN(key string, n int) bool {
	bucket := l.store.Get(key)
	tokens := refill(bucket, l.Rate, l.Burst, l.now())
	if tokens < float64(n) {
		l.store.Put(key, store.Bucket{Tokens: tokens, Updated: l.now()})
		return false
	}
	l.store.Put(key, store.Bucket{Tokens: tokens - float64(n), Updated: l.now()})
	return true
}

func refill(bucket store.Bucket, rate float64, burst int, now time.Time) float64 {
	if bucket.Updated.IsZero() {
		return float64(burst)
	}
	elapsed := now.Sub(bucket.Updated).Seconds()
	tokens := bucket.Tokens + elapsed*rate
	if tokens > float64(burst) {
		return float64(burst)
	}
	return tokens
}
