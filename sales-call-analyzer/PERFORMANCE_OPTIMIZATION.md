# Performance Optimization Guide

## Current Bottlenecks

1. **Whisper Transcription** - CPU-intensive, runs synchronously (~2-5x real-time on CPU)
2. **Synchronous Processing** - All steps block the request thread
3. **Single Worker** - Only 1 Gunicorn worker (due to previous in-memory storage)
4. **Model Size** - Using "base" model (74M) - slower but more accurate

## Quick Wins (Easy to Implement)

### 1. Use Smaller Whisper Model
**Impact: 3-5x faster transcription**
- Change `WHISPER_MODEL=tiny` in environment
- Trade-off: Slightly lower accuracy, but still good for sales calls
- **Speed**: tiny ~10x real-time, base ~2-3x real-time

### 2. Increase Workers (Now Safe with Database)
**Impact: Better concurrency**
- Change `--workers 1` to `--workers 2` or `--workers 4` in Dockerfile
- Now safe because we use database storage, not in-memory

### 3. Optimize Whisper Settings
**Impact: 20-30% faster**
- Use `fp16=False` explicitly (already done for CPU)
- Reduce beam size if using beam search
- Use faster decoding options

## Medium Effort (Background Jobs)

### 4. Background Job Processing
**Impact: Non-blocking, better UX**
- Move transcription to background thread/process
- Use threading.Thread or multiprocessing
- Update status via database, poll from frontend
- **Implementation**: ~2-3 hours

### 5. Progress Updates via Server-Sent Events (SSE)
**Impact: Better UX, feels faster**
- Stream progress updates during transcription
- Show "Transcribing... 45%" instead of just "Transcribing..."
- **Implementation**: ~1-2 hours

## Advanced (More Complex)

### 6. Use OpenAI Whisper API
**Impact: 5-10x faster, but sends audio externally**
- Trade-off: Privacy vs Speed
- Cost: ~$0.006 per minute
- **Implementation**: ~1 hour

### 7. GPU Acceleration
**Impact: 10-50x faster**
- Requires GPU-enabled instance
- Use CUDA with Whisper
- **Cost**: More expensive hosting

### 8. Celery + Redis for Distributed Processing
**Impact: Scalable, production-ready**
- Separate worker processes
- Queue system for jobs
- **Implementation**: ~4-6 hours

## Recommended Immediate Actions

1. **Switch to `tiny` model** (5 min change)
   ```bash
   # In Railway/environment
   WHISPER_MODEL=tiny
   ```

2. **Increase workers to 2-4** (2 min change)
   ```dockerfile
   --workers 2
   ```

3. **Add background processing** (2-3 hours)
   - Use threading for async transcription
   - Update status in database
   - Frontend polls for updates

## Implementation Priority

**Phase 1 (Do Now):**
- [ ] Switch to `tiny` Whisper model
- [ ] Increase workers to 2-4

**Phase 2 (This Week):**
- [ ] Add background job processing
- [ ] Add progress updates

**Phase 3 (Future):**
- [ ] Consider OpenAI Whisper API option
- [ ] Add GPU support if needed

