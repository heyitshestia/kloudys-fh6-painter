package gpu

import (
	"fmt"
	"math"
	"strings"
	"unsafe"

	"forza-painter-geometrize-go/internal/model"

	"github.com/jgillich/go-opencl/cl"
)

// ErrorGridSize is the side length of the downsampled error histogram used
// for biasing random candidate placement towards high-error regions.
const ErrorGridSize = 64

// ringSize is the number of candidate / result / grid host+device staging
// buffers kept in flight. With size 3 the engine can submit work for the
// next round while the previous round is still being read back, which is
// the foundation that lets us hide CPU candidate generation behind GPU
// kernels (e.g. apply + grid recompute) without ever stalling on a
// blocking transfer.
const ringSize = 3

// EvalResult holds the score and the optimal RGB color for a single
// evaluated candidate. RGB is computed analytically by the GPU; the engine
// stores it back into the candidate before applying the chosen shape.
type EvalResult struct {
	Score float32
	R     float32
	G     float32
	B     float32
}

// EvalTicket is returned by SubmitEval and consumed by WaitEval. It is
// just a typed handle into the evaluator's ring of in-flight slots; the
// sequence number guards against stale tickets being waited on twice.
type EvalTicket struct {
	slot  int
	seq   uint64
	count int
	valid bool
}

// GridTicket is the equivalent handle for an in-flight error-grid update.
type GridTicket struct {
	slot  int
	seq   uint64
	valid bool
}

// Valid reports whether the ticket refers to an actual in-flight
// submission. The zero value of GridTicket is invalid.
func (t GridTicket) Valid() bool { return t.valid }

// Valid reports whether the ticket refers to an actual in-flight
// submission. The zero value of EvalTicket is invalid.
func (t EvalTicket) Valid() bool { return t.valid }

type evalSlot struct {
	readEvt *cl.Event
	seq     uint64
	busy    bool
}

type gridSlot struct {
	readEvt *cl.Event
	seq     uint64
	busy    bool
}

type Evaluator struct {
	context     *cl.Context
	queue       *cl.CommandQueue
	program     *cl.Program
	evalKernel  *cl.Kernel
	evalKernelV4 *cl.Kernel
	applyKernel *cl.Kernel
	gridKernel  *cl.Kernel

	UseWorkGroupEval bool
	wgSize           int

	targetBuffer  *cl.MemObject
	currentBuffer *cl.MemObject
	maskBuffer    *cl.MemObject

	// Eval ring.
	candBuffers   [ringSize]*cl.MemObject
	resultBuffers [ringSize]*cl.MemObject
	hostCands     [ringSize][]float32
	hostResults   [ringSize][]float32
	evalSlots     [ringSize]evalSlot
	nextEvalSlot  int
	evalSeq       uint64

	// Grid ring.
	errorGridBufs  [ringSize]*cl.MemObject
	hostErrorGrids [ringSize][]float32
	gridSlots      [ringSize]gridSlot
	nextGridSlot   int
	gridSeq        uint64

	width         int
	height        int
	pixelCount    int
	maxCandidates int
	gridW         int
	gridH         int
}

func NewEvaluator(target, current []float32, mask []uint8, width, height int, maxCandidates int) (*Evaluator, error) {
	if len(target) != len(current) {
		return nil, fmt.Errorf("target/current length mismatch")
	}
	if len(mask) != width*height {
		return nil, fmt.Errorf("mask length mismatch")
	}
	if maxCandidates < 1 {
		return nil, fmt.Errorf("maxCandidates must be > 0")
	}

	platforms, err := cl.GetPlatforms()
	if err != nil {
		return nil, err
	}
	if len(platforms) == 0 {
		return nil, fmt.Errorf("no OpenCL platforms found")
	}

	var allDevices []*cl.Device
	for _, p := range platforms {
		devices, dErr := p.GetDevices(cl.DeviceTypeGPU)
		if dErr == nil {
			allDevices = append(allDevices, devices...)
		}
	}
	if len(allDevices) == 0 {
		for _, p := range platforms {
			devices, dErr := p.GetDevices(cl.DeviceTypeAll)
			if dErr == nil {
				allDevices = append(allDevices, devices...)
			}
		}
	}
	if len(allDevices) == 0 {
		return nil, fmt.Errorf("no OpenCL devices found")
	}

	var device *cl.Device
	var bestScore int64 = -1
	for _, d := range allDevices {
		score := scoreDevice(d)
		if score > bestScore {
			bestScore = score
			device = d
		}
	}
	if device == nil {
		return nil, fmt.Errorf("no suitable OpenCL device found")
	}

	fmt.Printf("OpenCL: Selected device %q (Vendor: %q, GPU: %v, Discrete: %v, VRAM: %dMB, Compute Units: %d)\n",
		device.Name(),
		device.Vendor(),
		device.Type()&cl.DeviceTypeGPU != 0,
		!device.HostUnifiedMemory(),
		device.GlobalMemSize()/(1024*1024),
		device.MaxComputeUnits(),
	)

	ctx, err := cl.CreateContext([]*cl.Device{device})
	if err != nil {
		return nil, err
	}

	queue, err := ctx.CreateCommandQueue(device, 0)
	if err != nil {
		ctx.Release()
		return nil, err
	}

	program, err := ctx.CreateProgramWithSource([]string{evaluateKernelSource})
	if err != nil {
		queue.Release()
		ctx.Release()
		return nil, err
	}
	if err := program.BuildProgram([]*cl.Device{device}, "-cl-fast-relaxed-math -cl-mad-enable"); err != nil {
		program.Release()
		queue.Release()
		ctx.Release()
		return nil, fmt.Errorf("failed building OpenCL program: %w", err)
	}

	evalKernel, err := program.CreateKernel("evaluate_candidates_v3")
	if err != nil {
		program.Release()
		queue.Release()
		ctx.Release()
		return nil, err
	}
	evalKernelV4, err := program.CreateKernel("evaluate_candidates_v4")
	if err != nil {
		evalKernel.Release()
		program.Release()
		queue.Release()
		ctx.Release()
		return nil, err
	}
	applyKernel, err := program.CreateKernel("apply_candidate_v2")
	if err != nil {
		evalKernelV4.Release()
		evalKernel.Release()
		program.Release()
		queue.Release()
		ctx.Release()
		return nil, err
	}
	gridKernel, err := program.CreateKernel("compute_error_grid")
	if err != nil {
		applyKernel.Release()
		evalKernelV4.Release()
		evalKernel.Release()
		program.Release()
		queue.Release()
		ctx.Release()
		return nil, err
	}

	gridW := ErrorGridSize
	gridH := ErrorGridSize
	if width < gridW {
		gridW = width
	}
	if height < gridH {
		gridH = height
	}
	if gridW < 1 {
		gridW = 1
	}
	if gridH < 1 {
		gridH = 1
	}

	e := &Evaluator{
		context:       ctx,
		queue:         queue,
		program:       program,
		evalKernel:    evalKernel,
		evalKernelV4:  evalKernelV4,
		applyKernel:   applyKernel,
		gridKernel:    gridKernel,
		wgSize:        16,
		width:         width,
		height:        height,
		pixelCount:    width * height,
		maxCandidates: maxCandidates,
		gridW:         gridW,
		gridH:         gridH,
	}

	cleanup := func() {
		for i := 0; i < ringSize; i++ {
			if e.candBuffers[i] != nil {
				e.candBuffers[i].Release()
			}
			if e.resultBuffers[i] != nil {
				e.resultBuffers[i].Release()
			}
			if e.errorGridBufs[i] != nil {
				e.errorGridBufs[i].Release()
			}
		}
		if e.maskBuffer != nil {
			e.maskBuffer.Release()
		}
		if e.currentBuffer != nil {
			e.currentBuffer.Release()
		}
		if e.targetBuffer != nil {
			e.targetBuffer.Release()
		}
		gridKernel.Release()
		applyKernel.Release()
		evalKernelV4.Release()
		evalKernel.Release()
		program.Release()
		queue.Release()
		ctx.Release()
	}

	if e.targetBuffer, err = ctx.CreateEmptyBuffer(cl.MemReadOnly, len(target)*4); err != nil {
		cleanup()
		return nil, err
	}
	if e.currentBuffer, err = ctx.CreateEmptyBuffer(cl.MemReadWrite, len(current)*4); err != nil {
		cleanup()
		return nil, err
	}
	if e.maskBuffer, err = ctx.CreateEmptyBuffer(cl.MemReadOnly, len(mask)); err != nil {
		cleanup()
		return nil, err
	}

	for i := 0; i < ringSize; i++ {
		buf, bErr := ctx.CreateEmptyBuffer(cl.MemReadOnly, maxCandidates*7*4)
		if bErr != nil {
			cleanup()
			return nil, bErr
		}
		e.candBuffers[i] = buf
		rbuf, rErr := ctx.CreateEmptyBuffer(cl.MemWriteOnly, maxCandidates*4*4)
		if rErr != nil {
			cleanup()
			return nil, rErr
		}
		e.resultBuffers[i] = rbuf
		gbuf, gErr := ctx.CreateEmptyBuffer(cl.MemReadWrite, gridW*gridH*4)
		if gErr != nil {
			cleanup()
			return nil, gErr
		}
		e.errorGridBufs[i] = gbuf

		e.hostCands[i] = make([]float32, maxCandidates*7)
		e.hostResults[i] = make([]float32, maxCandidates*4)
		e.hostErrorGrids[i] = make([]float32, gridW*gridH)
	}

	// Initial uploads. These are blocking because the engine has nothing
	// useful to do until the buffers are resident anyway. We still release
	// the returned events explicitly so the OpenCL runtime can free them
	// promptly instead of waiting for the Go finalizer to run.
	if evt, err := queue.EnqueueWriteBufferFloat32(e.targetBuffer, true, 0, target, nil); err != nil {
		cleanup()
		return nil, err
	} else if evt != nil {
		evt.Release()
	}
	if evt, err := queue.EnqueueWriteBufferFloat32(e.currentBuffer, true, 0, current, nil); err != nil {
		cleanup()
		return nil, err
	} else if evt != nil {
		evt.Release()
	}
	if evt, err := queue.EnqueueWriteBuffer(e.maskBuffer, true, 0, len(mask), unsafe.Pointer(&mask[0]), nil); err != nil {
		cleanup()
		return nil, err
	} else if evt != nil {
		evt.Release()
	}

	return e, nil
}

func (e *Evaluator) Close() {
	// Drain queue first so no async work touches buffers we are about to
	// release. Flush also clears every slot's event/busy bookkeeping, so
	// we don't need a second pass to release events here. Errors are
	// deliberately ignored - we are tearing down.
	_ = e.Flush()

	for i := 0; i < ringSize; i++ {
		if e.errorGridBufs[i] != nil {
			e.errorGridBufs[i].Release()
		}
		if e.resultBuffers[i] != nil {
			e.resultBuffers[i].Release()
		}
		if e.candBuffers[i] != nil {
			e.candBuffers[i].Release()
		}
	}
	if e.maskBuffer != nil {
		e.maskBuffer.Release()
	}
	if e.currentBuffer != nil {
		e.currentBuffer.Release()
	}
	if e.targetBuffer != nil {
		e.targetBuffer.Release()
	}
	if e.gridKernel != nil {
		e.gridKernel.Release()
	}
	if e.applyKernel != nil {
		e.applyKernel.Release()
	}
	if e.evalKernelV4 != nil {
		e.evalKernelV4.Release()
	}
	if e.evalKernel != nil {
		e.evalKernel.Release()
	}
	if e.program != nil {
		e.program.Release()
	}
	if e.queue != nil {
		e.queue.Release()
	}
	if e.context != nil {
		e.context.Release()
	}
}

func (e *Evaluator) SetTarget(target []float32) error {
	if e.queue == nil {
		return fmt.Errorf("evaluator is closed")
	}
	if len(target) != e.pixelCount*4 {
		return fmt.Errorf("target length mismatch")
	}
	if err := e.Flush(); err != nil {
		return err
	}
	if evt, err := e.queue.EnqueueWriteBufferFloat32(e.targetBuffer, true, 0, target, nil); err != nil {
		return err
	} else if evt != nil {
		evt.Release()
	}
	return nil
}

// Flush blocks until every command previously enqueued on the internal
// command queue has finished and clears the bookkeeping for in-flight
// slots so they can be reused. Useful at the end of the run or before
// reading data through paths that assume no pending work (e.g. preview).
func (e *Evaluator) Flush() error {
	if e.queue == nil {
		return nil
	}
	if err := e.queue.Finish(); err != nil {
		return err
	}
	for i := 0; i < ringSize; i++ {
		if e.evalSlots[i].busy && e.evalSlots[i].readEvt != nil {
			e.evalSlots[i].readEvt.Release()
			e.evalSlots[i].readEvt = nil
			e.evalSlots[i].busy = false
		}
		if e.gridSlots[i].busy && e.gridSlots[i].readEvt != nil {
			e.gridSlots[i].readEvt.Release()
			e.gridSlots[i].readEvt = nil
			e.gridSlots[i].busy = false
		}
	}
	return nil
}

// SubmitEval enqueues a candidate batch evaluation without blocking on the
// GPU. The caller must invoke WaitEval on the returned ticket before the
// host data backing the candidates becomes irrelevant; in practice the
// engine submits a batch, optionally does a tiny bit of CPU work, and then
// waits. The ring buffer guarantees that submitting more batches than the
// ring size is safe (the next slot is reclaimed with a defensive wait).
func (e *Evaluator) SubmitEval(cands []model.Candidate) (EvalTicket, error) {
	count := len(cands)
	if count == 0 {
		return EvalTicket{}, nil
	}
	if count > e.maxCandidates {
		return EvalTicket{}, fmt.Errorf("candidate count %d exceeds max %d", count, e.maxCandidates)
	}

	slot := e.nextEvalSlot
	e.nextEvalSlot = (e.nextEvalSlot + 1) % ringSize

	if e.evalSlots[slot].busy {
		// Engine forgot to consume an outstanding ticket; reclaim the slot.
		if err := cl.WaitForEvents([]*cl.Event{e.evalSlots[slot].readEvt}); err != nil {
			return EvalTicket{}, err
		}
		e.evalSlots[slot].readEvt.Release()
		e.evalSlots[slot].readEvt = nil
		e.evalSlots[slot].busy = false
	}

	packed := e.hostCands[slot][:count*7]
	for i, c := range cands {
		base := i * 7
		packed[base+0] = float32(c.Type)
		packed[base+1] = c.X
		packed[base+2] = c.Y
		packed[base+3] = c.RX
		packed[base+4] = c.RY
		packed[base+5] = c.Theta
		packed[base+6] = c.A
	}

	// Non-blocking write. The OpenCL spec snapshots the host pointer's
	// contents at command submission, but the runtime is allowed to defer
	// the actual transfer; either way our hostCands slot is not reused
	// until the ring wraps and reclaims it.
	writeEvt, err := e.queue.EnqueueWriteBufferFloat32(e.candBuffers[slot], false, 0, packed, nil)
	if err != nil {
		return EvalTicket{}, err
	}
	writeEvt.Release()

	if e.UseWorkGroupEval {
		if err := e.evalKernelV4.SetArgs(
			e.targetBuffer,
			e.currentBuffer,
			e.maskBuffer,
			e.candBuffers[slot],
			e.resultBuffers[slot],
			int32(e.width),
			int32(e.height),
		); err != nil {
			return EvalTicket{}, err
		}
		gs := e.wgSize
		kernelEvt, err := e.queue.EnqueueNDRangeKernel(
			e.evalKernelV4, nil,
			[]int{count * gs, gs},
			[]int{gs, gs},
			nil,
		)
		if err != nil {
			return EvalTicket{}, err
		}
		kernelEvt.Release()
	} else {
		if err := e.evalKernel.SetArgs(
			e.targetBuffer,
			e.currentBuffer,
			e.maskBuffer,
			e.candBuffers[slot],
			e.resultBuffers[slot],
			int32(e.width),
			int32(e.height),
		); err != nil {
			return EvalTicket{}, err
		}

		// clEnqueueNDRangeKernel snapshots its arguments at enqueue time, so
		// it is safe to set new args for a different slot in the next call
		// even though this kernel hasn't actually executed yet.
		kernelEvt, err := e.queue.EnqueueNDRangeKernel(e.evalKernel, nil, []int{count}, nil, nil)
		if err != nil {
			return EvalTicket{}, err
		}
		kernelEvt.Release()
	}

	flat := e.hostResults[slot][:count*4]
	readEvt, err := e.queue.EnqueueReadBufferFloat32(e.resultBuffers[slot], false, 0, flat, nil)
	if err != nil {
		return EvalTicket{}, err
	}

	e.evalSeq++
	e.evalSlots[slot] = evalSlot{
		readEvt: readEvt,
		seq:     e.evalSeq,
		busy:    true,
	}
	return EvalTicket{slot: slot, seq: e.evalSeq, count: count, valid: true}, nil
}

// WaitEval blocks until the given submission's read transfer completes and
// returns the per-candidate results. After this call the slot is freed and
// the ticket is exhausted.
func (e *Evaluator) WaitEval(t EvalTicket) ([]EvalResult, error) {
	if !t.valid {
		return nil, nil
	}
	s := &e.evalSlots[t.slot]
	if !s.busy || s.seq != t.seq {
		return nil, fmt.Errorf("WaitEval: stale or invalid ticket")
	}
	if err := cl.WaitForEvents([]*cl.Event{s.readEvt}); err != nil {
		return nil, err
	}
	s.readEvt.Release()
	s.readEvt = nil
	s.busy = false

	flat := e.hostResults[t.slot][:t.count*4]
	out := make([]EvalResult, t.count)
	for i := 0; i < t.count; i++ {
		out[i] = EvalResult{
			Score: flat[i*4+0],
			R:     flat[i*4+1],
			G:     flat[i*4+2],
			B:     flat[i*4+3],
		}
	}
	return out, nil
}

// Evaluate is the synchronous helper used by code paths that don't care
// about overlap. It is implemented in terms of Submit/Wait.
func (e *Evaluator) Evaluate(cands []model.Candidate) ([]EvalResult, error) {
	t, err := e.SubmitEval(cands)
	if err != nil {
		return nil, err
	}
	return e.WaitEval(t)
}

// SubmitApply enqueues a blend kernel for the given candidate without
// blocking. The in-order command queue guarantees that any subsequent
// SubmitEval / SubmitErrorGrid will observe the updated current canvas.
func (e *Evaluator) SubmitApply(candidate model.Candidate) error {
	rx := candidate.RX
	ry := candidate.RY
	if rx < 1 {
		rx = 1
	}
	if ry < 1 {
		ry = 1
	}
	theta := float64(candidate.Theta) * (math.Pi / 180.0)
	cosT := math.Cos(theta)
	sinT := math.Sin(theta)
	rx2 := float64(rx) * float64(rx)
	ry2 := float64(ry) * float64(ry)
	cos2 := cosT * cosT
	sin2 := sinT * sinT
	ex := 0.0
	ey := 0.0
	switch candidate.Type {
	case 1:
		ex = float64(rx)
		ey = float64(ry)
	case 2:
		ex = math.Abs(float64(rx)*cosT) + math.Abs(float64(ry)*sinT)
		ey = math.Abs(float64(rx)*sinT) + math.Abs(float64(ry)*cosT)
	default:
		ex = math.Sqrt(rx2*cos2 + ry2*sin2)
		ey = math.Sqrt(rx2*sin2 + ry2*cos2)
	}

	xMin := int(math.Floor(float64(candidate.X) - ex - 1.0))
	xMax := int(math.Ceil(float64(candidate.X) + ex + 1.0))
	yMin := int(math.Floor(float64(candidate.Y) - ey - 1.0))
	yMax := int(math.Ceil(float64(candidate.Y) + ey + 1.0))
	if xMin < 0 {
		xMin = 0
	}
	if yMin < 0 {
		yMin = 0
	}
	if xMax > e.width-1 {
		xMax = e.width - 1
	}
	if yMax > e.height-1 {
		yMax = e.height - 1
	}
	if xMax < xMin || yMax < yMin {
		return nil
	}

	bw := xMax - xMin + 1
	bh := yMax - yMin + 1

	if err := e.applyKernel.SetArgs(
		e.currentBuffer,
		e.maskBuffer,
		int32(e.width),
		int32(e.height),
		int32(candidate.Type),
		int32(xMin),
		int32(yMin),
		int32(xMax),
		int32(yMax),
		candidate.X,
		candidate.Y,
		candidate.RX,
		candidate.RY,
		candidate.Theta,
		candidate.R,
		candidate.G,
		candidate.B,
		candidate.A,
	); err != nil {
		return err
	}

	evt, err := e.queue.EnqueueNDRangeKernel(e.applyKernel, nil, []int{bw, bh}, nil, nil)
	if err != nil {
		return err
	}
	evt.Release()
	return nil
}

// Apply is the synchronous helper used by tests / single-call flows. It
// drains the queue via Flush so that any in-flight ticket events that
// happen to complete during the wait are also reaped, keeping the slot
// bookkeeping consistent with the async path.
func (e *Evaluator) Apply(candidate model.Candidate) error {
	if err := e.SubmitApply(candidate); err != nil {
		return err
	}
	return e.Flush()
}

// SubmitErrorGrid enqueues a downsampled error histogram computation and
// the corresponding readback without blocking. The histogram cells reflect
// the canvas state at the moment the kernel runs in the queue, i.e. after
// any apply commands previously submitted on the same queue.
func (e *Evaluator) SubmitErrorGrid() (GridTicket, error) {
	slot := e.nextGridSlot
	e.nextGridSlot = (e.nextGridSlot + 1) % ringSize

	if e.gridSlots[slot].busy {
		if err := cl.WaitForEvents([]*cl.Event{e.gridSlots[slot].readEvt}); err != nil {
			return GridTicket{}, err
		}
		e.gridSlots[slot].readEvt.Release()
		e.gridSlots[slot].readEvt = nil
		e.gridSlots[slot].busy = false
	}

	if err := e.gridKernel.SetArgs(
		e.targetBuffer,
		e.currentBuffer,
		e.maskBuffer,
		e.errorGridBufs[slot],
		int32(e.width),
		int32(e.height),
		int32(e.gridW),
		int32(e.gridH),
	); err != nil {
		return GridTicket{}, err
	}
	kernelEvt, err := e.queue.EnqueueNDRangeKernel(e.gridKernel, nil, []int{e.gridW, e.gridH}, nil, nil)
	if err != nil {
		return GridTicket{}, err
	}
	kernelEvt.Release()

	readEvt, err := e.queue.EnqueueReadBufferFloat32(e.errorGridBufs[slot], false, 0, e.hostErrorGrids[slot], nil)
	if err != nil {
		return GridTicket{}, err
	}

	e.gridSeq++
	e.gridSlots[slot] = gridSlot{
		readEvt: readEvt,
		seq:     e.gridSeq,
		busy:    true,
	}
	return GridTicket{slot: slot, seq: e.gridSeq, valid: true}, nil
}

// WaitErrorGrid blocks until the given submission's grid readback finishes
// and returns a copy of the grid plus its dimensions.
func (e *Evaluator) WaitErrorGrid(t GridTicket) ([]float32, int, int, error) {
	if !t.valid {
		return nil, 0, 0, fmt.Errorf("WaitErrorGrid: invalid ticket")
	}
	s := &e.gridSlots[t.slot]
	if !s.busy || s.seq != t.seq {
		return nil, 0, 0, fmt.Errorf("WaitErrorGrid: stale or invalid ticket")
	}
	if err := cl.WaitForEvents([]*cl.Event{s.readEvt}); err != nil {
		return nil, 0, 0, err
	}
	s.readEvt.Release()
	s.readEvt = nil
	s.busy = false
	out := make([]float32, len(e.hostErrorGrids[t.slot]))
	copy(out, e.hostErrorGrids[t.slot])
	return out, e.gridW, e.gridH, nil
}

// ErrorGrid is the synchronous helper retained for callers that don't
// care about overlap.
func (e *Evaluator) ErrorGrid() ([]float32, int, int, error) {
	t, err := e.SubmitErrorGrid()
	if err != nil {
		return nil, 0, 0, err
	}
	return e.WaitErrorGrid(t)
}

// ReadCurrent reads the entire current canvas back to host memory. The
// blocking read goes through the same in-order queue as everything else,
// so it serializes naturally after any pending apply / grid commands
// without us having to drain the queue (which would invalidate any
// outstanding GridTicket the caller is still holding).
func (e *Evaluator) ReadCurrent(dst []float32) error {
	if len(dst) != e.pixelCount*4 {
		return fmt.Errorf("destination length mismatch")
	}
	evt, err := e.queue.EnqueueReadBufferFloat32(e.currentBuffer, true, 0, dst, nil)
	if evt != nil {
		evt.Release()
	}
	return err
}

// GridDims returns the dimensions of the error histogram grid.
func (e *Evaluator) GridDims() (int, int) {
	return e.gridW, e.gridH
}

// ImageDims returns the working image dimensions.
func (e *Evaluator) ImageDims() (int, int) {
	return e.width, e.height
}

func scoreDevice(d *cl.Device) int64 {
	var score int64

	if d.Type()&cl.DeviceTypeGPU != 0 {
		score += 1_000_000_000_000
	}
	if !d.HostUnifiedMemory() {
		score += 500_000_000_000
	}

	memMB := d.GlobalMemSize() / (1024 * 1024)
	score += memMB * 10_000
	score += int64(d.MaxComputeUnits()) * 10_000

	vendor := strings.ToLower(d.Vendor())
	name := strings.ToLower(d.Name())
	if strings.Contains(vendor, "nvidia") || strings.Contains(name, "geforce") || strings.Contains(name, "rtx") {
		score += 5_000_000_000
	} else if strings.Contains(vendor, "amd") || strings.Contains(name, "radeon") {
		score += 3_000_000_000
	} else if strings.Contains(vendor, "intel") {
		score += 1_000_000_000
	}

	return score
}

// ResetCurrentBuffer clears/re-uploads the initial current canvas back to e.currentBuffer.
func (e *Evaluator) ResetCurrentBuffer(current []float32) error {
	if len(current) != e.pixelCount*4 {
		return fmt.Errorf("current slice length mismatch")
	}
	evt, err := e.queue.EnqueueWriteBufferFloat32(e.currentBuffer, true, 0, current, nil)
	if evt != nil {
		evt.Release()
	}
	return err
}
