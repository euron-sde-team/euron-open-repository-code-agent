// Package store keeps token buckets between requests.
package store

import (
	"sync"
	"time"
)

// Bucket is the persisted state of one key.
type Bucket struct {
	Tokens  float64
	Updated time.Time
}

// Store loads and saves buckets.
type Store interface {
	Get(key string) Bucket
	Put(key string, b Bucket)
}

// Memory is a Store for a single process.
type Memory struct {
	mu      sync.Mutex
	buckets map[string]Bucket
}

// NewMemory returns an empty in-memory store.
func NewMemory() *Memory {
	return &Memory{buckets: make(map[string]Bucket)}
}

// Get returns the bucket for key, or an empty one.
func (m *Memory) Get(key string) Bucket {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.buckets[key]
}

// Put saves the bucket for key.
func (m *Memory) Put(key string, b Bucket) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.buckets[key] = b
}
