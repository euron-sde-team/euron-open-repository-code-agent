package ratelimit

import (
	"testing"
	"time"

	"example.com/ratelimit/store"
)

func TestBurstThenRefuse(t *testing.T) {
	l := New(1, 3, store.NewMemory())
	for i := 0; i < 3; i++ {
		if !l.Allow("client") {
			t.Fatalf("event %d refused inside the burst", i)
		}
	}
	if l.Allow("client") {
		t.Fatal("event allowed beyond the burst")
	}
}

func TestRefillOverTime(t *testing.T) {
	now := time.Unix(1000, 0)
	l := New(2, 2, store.NewMemory())
	l.now = func() time.Time { return now }
	l.AllowN("client", 2)
	now = now.Add(time.Second)
	if !l.AllowN("client", 2) {
		t.Fatal("bucket did not refill")
	}
}
