package engine

import (
	"fmt"
	"math"
	"math/rand"
	"path/filepath"
	"runtime"
	"sync"
	"time"

	"forza-painter-geometrize-go/internal/config"
	"forza-painter-geometrize-go/internal/gpu"
	"forza-painter-geometrize-go/internal/imageutil"
	"forza-painter-geometrize-go/internal/model"
	"forza-painter-geometrize-go/internal/output"
	"forza-painter-geometrize-go/internal/render"
)

type Options struct {
	ImagePath     string
	SettingsPath  string
	Profile       string
	OutputPath    string
	PreviewPath   string
	WorkspaceRoot string
	Seed          int64
}

const (
	maxNoImproveRetries = 100
	minImproveDelta     = -1e-7
	shapeRectangle      = 1
	shapeRotRect        = 2
	shapeEllipse        = 8
	shapeRotEllipse     = 16

	// Hill climb tuning. The mutation budget from settings is split into
	// up to maxHillClimbRounds rounds; each round mutates the current best
	// shape geometry slightly, evaluates the batch on GPU, and keeps any
	// improvement before starting the next round.
	maxHillClimbRounds  = 32
	idealHillClimbBatch = 64
	minHillClimbRounds  = 1
)

func Run(opts Options) error {
	if opts.ImagePath == "" {
		return fmt.Errorf("image path is required")
	}
	if opts.WorkspaceRoot == "" {
		opts.WorkspaceRoot = "."
	}

	settingsPath, err := config.ResolveSettingsPath(opts.WorkspaceRoot, opts.SettingsPath, opts.Profile)
	if err != nil {
		return err
	}
	cfg, err := config.ParseSettings(settingsPath)
	if err != nil {
		return err
	}

	threads := cfg.MaxThreads
	if threads <= 0 {
		threads = runtime.NumCPU()
	}
	if threads < 1 {
		threads = 1
	}
	runtime.GOMAXPROCS(threads)

	prepared, err := imageutil.LoadAndPrepare(opts.ImagePath, cfg.MaxResolution, cfg.DetailMode)
	if err != nil {
		return err
	}

	maxBatch := cfg.RandomSamples
	if cfg.MutatedSamples > maxBatch {
		maxBatch = cfg.MutatedSamples
	}
	activeTarget := prepared.Target
	switchedToFullDetail := true
	switchToFullDetailAt := cfg.StopAt
	if (cfg.DetailMode == "coarse_first" || cfg.DetailMode == "coarse_balanced" || cfg.DetailMode == "coarse_strict") && len(prepared.ScoringTarget) == len(prepared.Target) {
		activeTarget = prepared.ScoringTarget
		switchedToFullDetail = false
		switchFraction := 0.70
		if cfg.DetailMode == "coarse_balanced" {
			switchFraction = 0.76
		}
		if cfg.DetailMode == "coarse_strict" {
			switchFraction = 0.82
		}
		switchToFullDetailAt = maxInt(1, int(math.Round(float64(cfg.StopAt)*switchFraction)))
	}

	evaluator, err := gpu.NewEvaluator(activeTarget, prepared.Current, prepared.OpaqueMask, prepared.Width, prepared.Height, maxBatch)
	if err != nil {
		return err
	}
	evaluator.UseWorkGroupEval = cfg.UseWorkGroupEval
	defer evaluator.Close()

	rng := rand.New(rand.NewSource(seedValue(opts.Seed)))
	currentError, opaquePixels := computeTotalError(activeTarget, prepared.Current, prepared.OpaqueMask)
	denom := float64(maxInt(1, opaquePixels*4))

	shapes := []model.Shape{backgroundShape(prepared, normalizeScore(currentError, denom))}

	moveStep, radiusStep := mutationSteps(prepared.Width, prepared.Height)
	hillClimbRounds, mutationsPerRound := planHillClimb(cfg.MutatedSamples)

	// Initial sampler is computed synchronously - the engine has nothing
	// useful to do until the first random batch can be sampled.
	initialGrid, gw, gh, err := evaluator.ErrorGrid()
	if err != nil {
		return err
	}
	sampler := newErrorSampler(initialGrid, gw, gh, prepared.Width, prepared.Height)
	var pendingGrid gpu.GridTicket // not valid initially

	fmt.Printf("Loaded image: %s (%dx%d), transparency=%v\n", opts.ImagePath, prepared.Width, prepared.Height, prepared.HasTransparency)
	fmt.Printf("Settings: stopAt=%d randomSamples=%d mutatedSamples=%d saveAt=%d saveEvery(preview)=%d\n",
		cfg.StopAt, cfg.RandomSamples, cfg.MutatedSamples, len(cfg.SaveAt), cfg.SaveEvery)
	fmt.Printf("Compatibility mode: forceOpaqueShapes=%v\n", cfg.ForceOpaqueShapes)
	fmt.Printf("Shape mode: %s\n", cfg.ShapeMode)
	fmt.Printf("Detail mode: %s\n", cfg.DetailMode)
	if !switchedToFullDetail {
		fmt.Printf("Detail mode switch: coarse scoring until shape %d, then full-detail scoring\n", switchToFullDetailAt)
	}
	fmt.Printf("CPU workers: %d\n", threads)
	fmt.Printf("Hill climb: %d rounds x %d mutations (move +/- %.1fpx, radius +/- %.1fpx, theta +/- 30deg)\n",
		hillClimbRounds, mutationsPerRound, moveStep, radiusStep)
	fmt.Println("Pipeline: async (in-order queue, ring=3; sampler 1-shape stale)")
	fmt.Println("Scoring mode: delta error with GPU-computed optimal color (negative = better)")

	acceptedShapes := 0
	consecutiveNoImprove := 0
	finalPruneAttempts := 0
	lastPrunedMilestone := 0
	const maxFinalPrunes = 5

	for acceptedShapes < cfg.StopAt {
		step := acceptedShapes + 1
		stepStart := time.Now()
		if !switchedToFullDetail && acceptedShapes >= switchToFullDetailAt {
			fmt.Printf("[%d/%d] Switching scoring target to full detail\n", step, cfg.StopAt)
			if pendingGrid.Valid() {
				if _, _, _, err := evaluator.WaitErrorGrid(pendingGrid); err != nil {
					return err
				}
				pendingGrid = gpu.GridTicket{}
			}
			if err := evaluator.SetTarget(prepared.Target); err != nil {
				return err
			}
			current := make([]float32, len(prepared.Current))
			if err := evaluator.ReadCurrent(current); err != nil {
				return err
			}
			currentError, _ = computeTotalError(prepared.Target, current, prepared.OpaqueMask)
			initialGrid, gw, gh, err := evaluator.ErrorGrid()
			if err != nil {
				return err
			}
			sampler = newErrorSampler(initialGrid, gw, gh, prepared.Width, prepared.Height)
			activeTarget = prepared.Target
			switchedToFullDetail = true
		}
		fmt.Printf("[%d/%d] Generating random samples (%d)...\n", step, cfg.StopAt, cfg.RandomSamples)
		// While we generate random candidates on the CPU, the GPU may
		// still be running the previous shape's apply + error-grid
		// kernels (queued non-blocking at the end of the last iteration).
		randomCands := randomCandidates(rng, prepared, cfg.RandomSamples, cfg.ForceOpaqueShapes, sampler, threads, cfg.ShapeMode)

		fmt.Printf("[%d/%d] Evaluating random sample batch on OpenCL (%d)...\n", step, cfg.StopAt, len(randomCands))
		best, bestScore, err := submitAndPickBest(evaluator, randomCands)
		if err != nil {
			return err
		}
		fmt.Printf("[%d/%d] Random best delta: %.6f\n", step, cfg.StopAt, bestScore)

		if hillClimbRounds > 0 && mutationsPerRound > 0 && bestScore < 0 {
			improved := 0
			for round := 0; round < hillClimbRounds; round++ {
				mutations := mutatedCandidates(rng, prepared, best, mutationsPerRound, cfg.ForceOpaqueShapes, moveStep, radiusStep, threads, cfg.ShapeMode)
				roundBest, roundScore, mutErr := submitAndPickBest(evaluator, mutations)
				if mutErr != nil {
					return mutErr
				}
				if roundScore < bestScore {
					bestScore = roundScore
					best = roundBest
					improved++
				}
			}
			fmt.Printf("[%d/%d] Hill climb best delta after %d rounds: %.6f (%d improvement(s))\n",
				step, cfg.StopAt, hillClimbRounds, bestScore, improved)
		}

		if bestScore >= minImproveDelta {
			consecutiveNoImprove++
			fmt.Printf("[%d/%d] No improvement (delta %.6f). Retry %d/%d\n", step, cfg.StopAt, bestScore, consecutiveNoImprove, maxNoImproveRetries)
			if consecutiveNoImprove >= maxNoImproveRetries {
				fmt.Printf("Stopped early: reached max retries without improvement (%d)\n", maxNoImproveRetries)
				break
			}
			// Image state didn't change, sampler & pendingGrid still
			// describe the right canvas state; just loop and retry with
			// fresh random candidates.
			continue
		}

		consecutiveNoImprove = 0

		// Quantize geometry + colour to the integer grid that will end
		// up in the JSON; apply that exact shape so the GPU canvas
		// matches what the game will render from the JSON later.
		final := quantizeCandidate(best, prepared.Width, prepared.Height, cfg.ForceOpaqueShapes)

		// Submit apply non-blocking; the in-order queue ensures any
		// follow-up eval / grid kernel sees the updated canvas.
		if err := evaluator.SubmitApply(final); err != nil {
			return err
		}
		currentError += float64(bestScore)
		if currentError < 0 {
			currentError = 0
		}
		shapes = append(shapes, toShape(final, normalizeScore(currentError, denom)))
		acceptedShapes++
		fmt.Printf("[%d/%d] Added %s #%d (delta %.6f)\n", acceptedShapes, cfg.StopAt, shapeLabel(final.Type), len(shapes)-1, bestScore)

		savedCheckpoint := false
		if shouldSave(acceptedShapes, cfg) {
			if err := saveShapes(opts, shapes, acceptedShapes); err != nil {
				return err
			}
			savedCheckpoint = true
			fmt.Printf("[%d/%d] Saved geometry checkpoint for shape count %d\n", acceptedShapes, cfg.StopAt, acceptedShapes)
		}

		if savedCheckpoint || shouldSavePreview(acceptedShapes, cfg) {
			if err := savePreviewSnapshot(opts, shapes, prepared.Width, prepared.Height, acceptedShapes); err != nil {
				return err
			}
			if opts.PreviewPath != "" {
				if savedCheckpoint {
					fmt.Printf("[%d/%d] Saved preview snapshot for checkpoint %d\n", acceptedShapes, cfg.StopAt, acceptedShapes)
				} else {
					fmt.Printf("[%d/%d] Saved preview snapshot\n", acceptedShapes, cfg.StopAt)
				}
			}
		}

		isMilestonePass := acceptedShapes > 0 && acceptedShapes%500 == 0 && acceptedShapes > lastPrunedMilestone
		isFinalPass := acceptedShapes == cfg.StopAt && finalPruneAttempts < maxFinalPrunes

		if isMilestonePass || isFinalPass {
			if isFinalPass {
				fmt.Printf("[%d/%d] Reached target! Running final occlusion culling and compaction pass (%d/%d)...\n",
					acceptedShapes, cfg.StopAt, finalPruneAttempts+1, maxFinalPrunes)
			} else {
				fmt.Printf("[%d/%d] Scanning for completely occluded shapes to recycle...\n", acceptedShapes, cfg.StopAt)
			}

			if err := evaluator.Flush(); err != nil {
				return err
			}
			pendingGrid = gpu.GridTicket{}

			if isMilestonePass {
				lastPrunedMilestone = acceptedShapes
			}

			pruned := pruneOccludedShapes(shapes, prepared.Width, prepared.Height, prepared.OpaqueMask)
			removedCount := len(shapes) - len(pruned)

			if removedCount > 0 {
				if isFinalPass {
					fmt.Printf("[%d/%d] Recycled %d occluded shapes in final pass! Active shapes: %d -> %d\n",
						acceptedShapes, cfg.StopAt, removedCount, len(shapes), len(pruned))
					finalPruneAttempts++
				} else {
					fmt.Printf("[%d/%d] Recycled %d occluded shapes! Active shapes: %d -> %d\n",
						acceptedShapes, cfg.StopAt, removedCount, len(shapes), len(pruned))
				}

				shapes = pruned
				acceptedShapes = len(shapes) - 1

				if err := evaluator.ResetCurrentBuffer(prepared.Current); err != nil {
					return err
				}
				for _, s := range shapes[1:] {
					cand := model.Candidate{
						Type:  shapeFromShapeJSONType(s.Type),
						X:     float32(s.Data[0]),
						Y:     float32(s.Data[1]),
						RX:    shapeRadiusX(s),
						RY:    shapeRadiusY(s),
						Theta: shapeTheta(s),
						R:     float32(s.Color[0]) / 255.0,
						G:     float32(s.Color[1]) / 255.0,
						B:     float32(s.Color[2]) / 255.0,
						A:     float32(s.Color[3]) / 255.0,
					}
					if err := evaluator.SubmitApply(cand); err != nil {
						return err
					}
				}
				if err := evaluator.Flush(); err != nil {
					return err
				}
			} else {
				if isFinalPass {
					fmt.Printf("[%d/%d] Final pass: No occluded shapes found. Ready to finish.\n", acceptedShapes, cfg.StopAt)
				} else {
					fmt.Printf("[%d/%d] No occluded shapes found to recycle.\n", acceptedShapes, cfg.StopAt)
				}
			}
		}

		// Consume the previous shape's grid (its read finished long ago,
		// so this is essentially a free poll) and rebuild the sampler
		// from it. The sampler now reflects the canvas state one shape
		// behind real time; that's the cost of overlapping CPU random
		// generation with the GPU pipeline. Quality impact is negligible
		// because one shape changes <1% of pixels.
		if pendingGrid.Valid() {
			grid, gridW, gridH, gErr := evaluator.WaitErrorGrid(pendingGrid)
			if gErr != nil {
				return gErr
			}
			sampler = newErrorSampler(grid, gridW, gridH, prepared.Width, prepared.Height)
			pendingGrid = gpu.GridTicket{}
		}

		// Submit the grid kernel for the canvas-just-applied. It's
		// queued behind the apply; we'll consume the result next
		// iteration.
		newTicket, gErr := evaluator.SubmitErrorGrid()
		if gErr != nil {
			return gErr
		}
		pendingGrid = newTicket

		fmt.Printf("[%d/%d] Step completed in %s\n", acceptedShapes, cfg.StopAt, time.Since(stepStart).Round(time.Millisecond))
	}

	if acceptedShapes < cfg.StopAt {
		fmt.Printf("Finished early with %d/%d shapes due to no-improvement stopping rule\n", acceptedShapes, cfg.StopAt)
	}

	// Drain any pending grid ticket so its event is released cleanly.
	if pendingGrid.Valid() {
		if _, _, _, err := evaluator.WaitErrorGrid(pendingGrid); err != nil {
			return err
		}
		pendingGrid = gpu.GridTicket{}
	}

	if err := output.SaveGeometry(output.BuildFinalOutputPath(resolveOutputBase(opts)), shapes); err != nil {
		return err
	}

	if opts.PreviewPath != "" {
		if err := render.SaveShapePreviewPNG(opts.PreviewPath, shapes, prepared.Width, prepared.Height); err != nil {
			return err
		}
	}

	return nil
}

func seedValue(seed int64) int64 {
	if seed != 0 {
		return seed
	}
	return time.Now().UnixNano()
}

func backgroundShape(p *imageutil.PreparedImage, score float64) model.Shape {
	return model.Shape{
		Type:  1,
		Data:  []int{0, 0, p.Width, p.Height},
		Color: []int{int(p.BackgroundRGBA[0]), int(p.BackgroundRGBA[1]), int(p.BackgroundRGBA[2]), int(p.BackgroundRGBA[3])},
		Score: score,
	}
}

// planHillClimb splits the configured mutation budget into a number of
// rounds and a per-round batch size. We aim for ~64 candidates per round
// to keep the GPU occupied while still giving the climb enough steps to
// walk uphill instead of just sampling around the random seed.
func planHillClimb(budget int) (rounds, perRound int) {
	if budget <= 0 {
		return 0, 0
	}
	rounds = budget / idealHillClimbBatch
	if rounds < minHillClimbRounds {
		rounds = minHillClimbRounds
	}
	if rounds > maxHillClimbRounds {
		rounds = maxHillClimbRounds
	}
	perRound = budget / rounds
	if perRound < 1 {
		perRound = 1
	}
	return rounds, perRound
}

func mutationSteps(width, height int) (move, radius float32) {
	diag := math.Sqrt(float64(width*width) + float64(height*height))
	move = float32(math.Max(2.0, diag*0.012))
	radius = float32(math.Max(2.0, diag*0.010))
	return move, radius
}

// errorSampler converts the GPU-produced error histogram into a CDF that
// can be sampled in O(log n) per draw. It is rebuilt every accepted shape.
type errorSampler struct {
	gridW, gridH int
	imgW, imgH   int
	cdf          []float64
	total        float64
}

func newErrorSampler(grid []float32, gridW, gridH, imgW, imgH int) *errorSampler {
	cdf := make([]float64, len(grid))
	var total float64
	for i, v := range grid {
		if v < 0 {
			v = 0
		}
		total += float64(v)
		cdf[i] = total
	}
	return &errorSampler{
		gridW: gridW,
		gridH: gridH,
		imgW:  imgW,
		imgH:  imgH,
		cdf:   cdf,
		total: total,
	}
}

func (s *errorSampler) sample(rng *rand.Rand) (float32, float32) {
	// Defensive nil-check first so the fallback below can safely deref s.
	if s == nil {
		return 0, 0
	}
	if s.total <= 0 || s.gridW <= 0 || s.gridH <= 0 {
		return rng.Float32() * float32(s.imgW), rng.Float32() * float32(s.imgH)
	}
	u := rng.Float64() * s.total
	lo, hi := 0, len(s.cdf)-1
	for lo < hi {
		mid := (lo + hi) / 2
		if s.cdf[mid] < u {
			lo = mid + 1
		} else {
			hi = mid
		}
	}
	cell := lo
	gx := cell % s.gridW
	gy := cell / s.gridW
	x0 := int(int64(gx) * int64(s.imgW) / int64(s.gridW))
	x1 := int(int64(gx+1) * int64(s.imgW) / int64(s.gridW))
	y0 := int(int64(gy) * int64(s.imgH) / int64(s.gridH))
	y1 := int(int64(gy+1) * int64(s.imgH) / int64(s.gridH))
	if x1 <= x0 {
		x1 = x0 + 1
	}
	if y1 <= y0 {
		y1 = y0 + 1
	}
	if x1 > s.imgW {
		x1 = s.imgW
	}
	if y1 > s.imgH {
		y1 = s.imgH
	}
	x := float32(x0) + rng.Float32()*float32(x1-x0)
	y := float32(y0) + rng.Float32()*float32(y1-y0)
	return x, y
}

// randomCandidates seeds candidates whose CENTER is biased towards the
// regions of the image that still have the most error. Geometry (radius,
// angle) is randomized; color is left zero because the GPU evaluator
// computes the optimal color analytically and writes it back in the
// EvalResult.
func randomCandidates(rng *rand.Rand, prepared *imageutil.PreparedImage, count int, forceOpaque bool, sampler *errorSampler, workers int, shapeMode string) []model.Candidate {
	if count <= 0 {
		return []model.Candidate{{
			Type:  shapeRotEllipse,
			X:     float32(prepared.Width) * 0.5,
			Y:     float32(prepared.Height) * 0.5,
			RX:    4,
			RY:    4,
			Theta: 0,
			A:     1.0,
		}}
	}

	workers = clampWorkers(workers, count)
	seeds := workerSeeds(rng, workers)
	out := make([]model.Candidate, count)
	w := float32(prepared.Width)
	h := float32(prepared.Height)
	diag := float32(math.Sqrt(float64(prepared.Width*prepared.Width) + float64(prepared.Height*prepared.Height)))
	maxRadius := diag * 0.25
	if maxRadius < 4 {
		maxRadius = 4
	}
	minRadius := float32(2)

	var wg sync.WaitGroup
	chunk := (count + workers - 1) / workers
	for worker := 0; worker < workers; worker++ {
		start := worker * chunk
		end := start + chunk
		if end > count {
			end = count
		}
		if start >= end {
			break
		}
		wg.Add(1)
		go func(start, end int, seed int64) {
			defer wg.Done()
			localRNG := rand.New(rand.NewSource(seed))
			for i := start; i < end; i++ {
				shapeType := chooseShapeType(localRNG, shapeMode)
				x, y := sampler.sample(localRNG)
				if x < 0 {
					x = 0
				}
				if y < 0 {
					y = 0
				}
				if x > w-1 {
					x = w - 1
				}
				if y > h-1 {
					y = h - 1
				}
				alpha := float32(1.0)
				if !forceOpaque {
					alpha = randRange(localRNG, 0.3, 1.0)
				}
				theta := float32(0.0)
				if shapeUsesRotation(shapeType) {
					theta = localRNG.Float32() * 360
				}
				out[i] = model.Candidate{
					Type:  shapeType,
					X:     x,
					Y:     y,
					RX:    randRange(localRNG, minRadius, maxRadius),
					RY:    randRange(localRNG, minRadius, maxRadius),
					Theta: theta,
					A:     alpha,
				}
			}
		}(start, end, seeds[worker])
	}
	wg.Wait()
	return out
}

// mutatedCandidates only perturbs geometry. Colors are recomputed by the
// GPU on each evaluation, so seeding them on the CPU side would be wasted
// work (and would constrain the search).
func mutatedCandidates(rng *rand.Rand, prepared *imageutil.PreparedImage, base model.Candidate, count int, forceOpaque bool, moveStep, radiusStep float32, workers int, shapeMode string) []model.Candidate {
	if count <= 0 {
		return []model.Candidate{base}
	}

	workers = clampWorkers(workers, count)
	seeds := workerSeeds(rng, workers)
	out := make([]model.Candidate, count)
	w := float32(prepared.Width)
	h := float32(prepared.Height)
	var wg sync.WaitGroup
	chunk := (count + workers - 1) / workers
	for worker := 0; worker < workers; worker++ {
		start := worker * chunk
		end := start + chunk
		if end > count {
			end = count
		}
		if start >= end {
			break
		}
		wg.Add(1)
		go func(start, end int, seed int64) {
			defer wg.Done()
			localRNG := rand.New(rand.NewSource(seed))
			for i := start; i < end; i++ {
				cand := base
				if shapeModeAllowsFamilyMorph(shapeMode) && localRNG.Float32() < shapeModeMorphChance(shapeMode) {
					nextType := chooseShapeType(localRNG, shapeMode)
					if nextType != cand.Type {
						cand.Type = nextType
						if shapeUsesRotation(cand.Type) {
							cand.Theta = randRange(localRNG, 0, 360)
						} else {
							cand.Theta = 0
						}
					}
				}
				cand.X += randRange(localRNG, -moveStep, moveStep)
				cand.Y += randRange(localRNG, -moveStep, moveStep)
				if cand.X < 0 {
					cand.X = 0
				}
				if cand.Y < 0 {
					cand.Y = 0
				}
				if cand.X > w-1 {
					cand.X = w - 1
				}
				if cand.Y > h-1 {
					cand.Y = h - 1
				}
				cand.RX = float32(math.Max(1, float64(cand.RX+randRange(localRNG, -radiusStep, radiusStep))))
				cand.RY = float32(math.Max(1, float64(cand.RY+randRange(localRNG, -radiusStep, radiusStep))))
				if shapeUsesRotation(cand.Type) {
					cand.Theta += randRange(localRNG, -30, 30)
					if cand.Theta < 0 {
						cand.Theta += 360
					}
					if cand.Theta >= 360 {
						cand.Theta -= 360
					}
				} else {
					cand.Theta = 0
				}
				if forceOpaque {
					cand.A = 1.0
				}
				out[i] = cand
			}
		}(start, end, seeds[worker])
	}
	wg.Wait()
	return out
}

func clampWorkers(workers, count int) int {
	if workers <= 0 {
		workers = runtime.NumCPU()
	}
	if workers < 1 {
		workers = 1
	}
	if workers > count {
		workers = count
	}
	return workers
}

func workerSeeds(rng *rand.Rand, workers int) []int64 {
	seeds := make([]int64, workers)
	for i := 0; i < workers; i++ {
		seeds[i] = rng.Int63()
	}
	return seeds
}

// submitAndPickBest submits a candidate batch, waits for the result and
// returns the lowest-score candidate with its GPU-computed optimal color
// merged in. This is the tight inner loop of both random sampling and
// hill climb.
func submitAndPickBest(e *gpu.Evaluator, cands []model.Candidate) (model.Candidate, float32, error) {
	t, err := e.SubmitEval(cands)
	if err != nil {
		return model.Candidate{}, 0, err
	}
	results, err := e.WaitEval(t)
	if err != nil {
		return model.Candidate{}, 0, err
	}
	if len(results) == 0 {
		return model.Candidate{}, 0, fmt.Errorf("no candidate scores returned")
	}
	bestIdx := 0
	bestScore := results[0].Score
	for i := 1; i < len(results); i++ {
		if results[i].Score < bestScore {
			bestScore = results[i].Score
			bestIdx = i
		}
	}
	best := cands[bestIdx]
	best.R = results[bestIdx].R
	best.G = results[bestIdx].G
	best.B = results[bestIdx].B
	return best, bestScore, nil
}

func toShape(c model.Candidate, score float64) model.Shape {
	angle := int(math.Round(float64(c.Theta))) % 360
	if angle < 0 {
		angle += 360
	}
	if angle == 0 && c.Theta > 359.5 {
		angle = 360
	}
	switch c.Type {
	case shapeRectangle:
		return model.Shape{
			Type: shapeRectangle,
			Data: []int{
				int(math.Round(float64(c.X))),
				int(math.Round(float64(c.Y))),
				maxInt(1, int(math.Round(float64(c.RX*2)))),
				maxInt(1, int(math.Round(float64(c.RY*2)))),
			},
			Color: []int{int(f32ToByte(c.R)), int(f32ToByte(c.G)), int(f32ToByte(c.B)), int(f32ToByte(c.A))},
			Score: score,
		}
	case shapeRotRect:
		return model.Shape{
			Type: shapeRotRect,
			Data: []int{
				int(math.Round(float64(c.X))),
				int(math.Round(float64(c.Y))),
				maxInt(1, int(math.Round(float64(c.RX*2)))),
				maxInt(1, int(math.Round(float64(c.RY*2)))),
				angle,
			},
			Color: []int{int(f32ToByte(c.R)), int(f32ToByte(c.G)), int(f32ToByte(c.B)), int(f32ToByte(c.A))},
			Score: score,
		}
	case shapeEllipse:
		return model.Shape{
			Type: shapeRotEllipse,
			Data: []int{
				int(math.Round(float64(c.X))),
				int(math.Round(float64(c.Y))),
				maxInt(1, int(math.Round(float64(c.RX)))),
				maxInt(1, int(math.Round(float64(c.RY)))),
				0,
			},
			Color: []int{int(f32ToByte(c.R)), int(f32ToByte(c.G)), int(f32ToByte(c.B)), int(f32ToByte(c.A))},
			Score: score,
		}
	default:
		return model.Shape{
			Type: shapeRotEllipse,
			Data: []int{
				int(math.Round(float64(c.X))),
				int(math.Round(float64(c.Y))),
				maxInt(1, int(math.Round(float64(c.RX)))),
				maxInt(1, int(math.Round(float64(c.RY)))),
				angle,
			},
			Color: []int{int(f32ToByte(c.R)), int(f32ToByte(c.G)), int(f32ToByte(c.B)), int(f32ToByte(c.A))},
			Score: score,
		}
	}
}

func f32ToByte(v float32) uint8 {
	if v < 0 {
		v = 0
	}
	if v > 1 {
		v = 1
	}
	return uint8(math.Round(float64(v * 255)))
}

func shouldSave(step int, cfg model.Settings) bool {
	_, ok := cfg.SaveAt[step]
	return ok
}

func shouldSavePreview(step int, cfg model.Settings) bool {
	if cfg.SaveEvery < 1 {
		return false
	}
	return step%cfg.SaveEvery == 0
}

func saveShapes(opts Options, shapes []model.Shape, step int) error {
	base := resolveOutputBase(opts)
	return output.SaveGeometry(output.BuildOutputPath(base, step), shapes)
}

func resolveOutputBase(opts Options) string {
	if opts.OutputPath != "" {
		return opts.OutputPath
	}
	ext := filepath.Ext(opts.ImagePath)
	if ext == "" {
		return opts.ImagePath
	}
	return opts.ImagePath
}

func randRange(rng *rand.Rand, minV, maxV float32) float32 {
	return minV + (maxV-minV)*rng.Float32()
}

func savePreviewSnapshot(opts Options, shapes []model.Shape, width, height, step int) error {
	if opts.PreviewPath == "" {
		return nil
	}
	ext := filepath.Ext(opts.PreviewPath)
	base := opts.PreviewPath
	if ext != "" {
		base = opts.PreviewPath[:len(opts.PreviewPath)-len(ext)]
	}
	outPath := fmt.Sprintf("%s.%d.png", base, step)
	return render.SaveShapePreviewPNG(outPath, shapes, width, height)
}

func computeTotalError(target, current []float32, opaqueMask []uint8) (float64, int) {
	if len(target) != len(current) {
		return 0, 0
	}
	total := 0.0
	opaquePixels := 0
	for p := 0; p < len(opaqueMask); p++ {
		if opaqueMask[p] == 0 {
			continue
		}
		opaquePixels++
		idx := p * 4
		dr := float64(target[idx+0] - current[idx+0])
		dg := float64(target[idx+1] - current[idx+1])
		db := float64(target[idx+2] - current[idx+2])
		da := float64(target[idx+3] - current[idx+3])
		total += dr*dr + dg*dg + db*db + da*da
	}
	return total, opaquePixels
}

func normalizeScore(totalError, denom float64) float64 {
	if denom <= 0 {
		return 0
	}
	value := totalError / denom
	if value < 0 {
		value = 0
	}
	return math.Round(value*1_000_000) / 1_000_000
}

// quantizeCandidate is now only invoked at acceptance time. The GPU
// search runs on full-precision floats; the final shape that is committed
// both to the canvas and to the JSON gets snapped to the integer grid the
// game expects (pixel positions, integer angle, 8-bit colour).
func quantizeCandidate(c model.Candidate, width, height int, forceOpaque bool) model.Candidate {
	c.X = float32(clampInt(int(math.Round(float64(c.X))), 0, maxInt(0, width-1)))
	c.Y = float32(clampInt(int(math.Round(float64(c.Y))), 0, maxInt(0, height-1)))
	c.RX = float32(maxInt(1, int(math.Round(float64(c.RX)))))
	c.RY = float32(maxInt(1, int(math.Round(float64(c.RY)))))

	angle := int(math.Round(float64(c.Theta))) % 360
	if angle < 0 {
		angle += 360
	}
	if angle == 0 && c.Theta > 359.5 {
		angle = 360
	}
	if shapeUsesRotation(c.Type) {
		c.Theta = float32(angle)
	} else {
		c.Theta = 0
	}

	if forceOpaque {
		c.A = 1.0
	}
	c.R = float32(f32ToByte(c.R)) / 255.0
	c.G = float32(f32ToByte(c.G)) / 255.0
	c.B = float32(f32ToByte(c.B)) / 255.0
	c.A = float32(f32ToByte(c.A)) / 255.0
	return c
}

func shapeFromShapeJSONType(shapeType int) int {
	switch shapeType {
	case shapeRectangle:
		return shapeRectangle
	case shapeRotRect:
		return shapeRotRect
	case shapeRotEllipse:
		return shapeRotEllipse
	default:
		return shapeEllipse
	}
}

func shapeRadiusX(s model.Shape) float32 {
	if len(s.Data) < 4 {
		return 1
	}
	switch s.Type {
	case shapeRectangle, shapeRotRect:
		return float32(maxInt(1, s.Data[2]/2))
	default:
		return float32(maxInt(1, s.Data[2]))
	}
}

func shapeRadiusY(s model.Shape) float32 {
	if len(s.Data) < 4 {
		return 1
	}
	switch s.Type {
	case shapeRectangle, shapeRotRect:
		return float32(maxInt(1, s.Data[3]/2))
	default:
		return float32(maxInt(1, s.Data[3]))
	}
}

func shapeTheta(s model.Shape) float32 {
	if len(s.Data) >= 5 {
		return float32(s.Data[4])
	}
	return 0
}

func pruneOccludedShapes(shapes []model.Shape, width, height int, opaqueMask []uint8) []model.Shape {
	if len(shapes) <= 1 {
		return shapes
	}

	cov := make([]uint8, width*height)
	keep := make([]bool, len(shapes))
	keep[0] = true

	for j := len(shapes) - 1; j >= 1; j-- {
		s := shapes[j]
		if len(s.Data) < 4 {
			keep[j] = true
			continue
		}

		cx := float32(s.Data[0])
		cy := float32(s.Data[1])
		rx := shapeRadiusX(s)
		ry := shapeRadiusY(s)
		theta := shapeTheta(s)
		alpha := 255
		if len(s.Color) >= 4 {
			alpha = s.Color[3]
		}

		if rx < 1 {
			rx = 1
		}
		if ry < 1 {
			ry = 1
		}

		t := float64(theta) * (math.Pi / 180.0)
		cosT := float32(math.Cos(t))
		sinT := float32(math.Sin(t))
		invRX2 := float32(1.0) / (rx * rx)
		invRY2 := float32(1.0) / (ry * ry)

		xMin := clampInt(int(cx-rx-1), 0, width-1)
		xMax := clampInt(int(cx+rx+1), 0, width-1)
		yMin := clampInt(int(cy-ry-1), 0, height-1)
		yMax := clampInt(int(cy+ry+1), 0, height-1)

		isOccluded := true
		hasOpaquePixelsInsideMask := false

		for y := yMin; y <= yMax; y++ {
			for x := xMin; x <= xMax; x++ {
				p := y*width + x
				if opaqueMask[p] == 0 {
					continue
				}
				dx := float32(x) + 0.5 - cx
				dy := float32(y) + 0.5 - cy
				xr := dx*cosT + dy*sinT
				yr := -dx*sinT + dy*cosT

				inside := false
				switch s.Type {
				case shapeRectangle:
					inside = float32(math.Abs(float64(dx))) <= rx && float32(math.Abs(float64(dy))) <= ry
				case shapeRotRect:
					inside = float32(math.Abs(float64(xr))) <= rx && float32(math.Abs(float64(yr))) <= ry
				case shapeEllipse:
					inside = dx*dx*invRX2+dy*dy*invRY2 <= 1.0
				default:
					inside = xr*xr*invRX2+yr*yr*invRY2 <= 1.0
				}
				if !inside {
					continue
				}

				hasOpaquePixelsInsideMask = true
				if cov[p] == 0 {
					isOccluded = false
					break
				}
			}
			if !isOccluded {
				break
			}
		}

		if !hasOpaquePixelsInsideMask {
			isOccluded = true
		}

		if isOccluded {
			keep[j] = false
			continue
		}

		keep[j] = true
		if alpha == 255 {
			for y := yMin; y <= yMax; y++ {
				for x := xMin; x <= xMax; x++ {
					p := y*width + x
					if opaqueMask[p] == 0 {
						continue
					}
					dx := float32(x) + 0.5 - cx
					dy := float32(y) + 0.5 - cy
					xr := dx*cosT + dy*sinT
					yr := -dx*sinT + dy*cosT

					inside := false
					switch s.Type {
					case shapeRectangle:
						inside = float32(math.Abs(float64(dx))) <= rx && float32(math.Abs(float64(dy))) <= ry
					case shapeRotRect:
						inside = float32(math.Abs(float64(xr))) <= rx && float32(math.Abs(float64(yr))) <= ry
					case shapeEllipse:
						inside = dx*dx*invRX2+dy*dy*invRY2 <= 1.0
					default:
						inside = xr*xr*invRX2+yr*yr*invRY2 <= 1.0
					}
					if inside {
						cov[p] = 1
					}
				}
			}
		}
	}

	out := make([]model.Shape, 0, len(shapes))
	for i, ok := range keep {
		if ok {
			out = append(out, shapes[i])
		}
	}
	return out
}

func shapeUsesRotation(shapeType int) bool {
	return shapeType == shapeRotRect || shapeType == shapeRotEllipse
}

func chooseShapeType(rng *rand.Rand, shapeMode string) int {
	switch normalizeShapeMode(shapeMode) {
	case "rectangle":
		return shapeRectangle
	case "rotated_rectangle":
		return shapeRotRect
	case "ellipse":
		return shapeEllipse
	case "rotated_ellipse":
		return shapeRotEllipse
	case "mixed_rectangles":
		if rng.Float32() < 0.5 {
			return shapeRectangle
		}
		return shapeRotRect
	case "mixed_ellipses":
		if rng.Float32() < 0.5 {
			return shapeEllipse
		}
		return shapeRotEllipse
	case "mixed_edge_bias":
		u := rng.Float32()
		switch {
		case u < 0.10:
			return shapeRectangle
		case u < 0.55:
			return shapeRotRect
		case u < 0.72:
			return shapeEllipse
		default:
			return shapeRotEllipse
		}
	case "mixed_soft_detail":
		u := rng.Float32()
		switch {
		case u < 0.08:
			return shapeRectangle
		case u < 0.30:
			return shapeRotRect
		case u < 0.60:
			return shapeEllipse
		default:
			return shapeRotEllipse
		}
	case "mixed_smart_detail":
		u := rng.Float32()
		switch {
		case u < 0.10:
			return shapeRectangle
		case u < 0.42:
			return shapeRotRect
		case u < 0.66:
			return shapeEllipse
		default:
			return shapeRotEllipse
		}
	default:
		u := rng.Float32()
		switch {
		case u < 0.18:
			return shapeRectangle
		case u < 0.50:
			return shapeRotRect
		case u < 0.68:
			return shapeEllipse
		default:
			return shapeRotEllipse
		}
	}
}

func normalizeShapeMode(shapeMode string) string {
	switch shapeMode {
	case "rectangle", "rotated_rectangle", "ellipse", "rotated_ellipse", "mixed_rectangles", "mixed_ellipses", "mixed_default", "mixed_edge_bias", "mixed_soft_detail", "mixed_smart_detail":
		return shapeMode
	default:
		return "mixed_default"
	}
}

func shapeModeAllowsFamilyMorph(shapeMode string) bool {
	switch normalizeShapeMode(shapeMode) {
	case "mixed_rectangles", "mixed_ellipses", "mixed_default", "mixed_edge_bias", "mixed_soft_detail", "mixed_smart_detail":
		return true
	default:
		return false
	}
}

func shapeModeMorphChance(shapeMode string) float32 {
	switch normalizeShapeMode(shapeMode) {
	case "mixed_edge_bias":
		return 0.10
	case "mixed_soft_detail":
		return 0.07
	case "mixed_smart_detail":
		return 0.09
	case "mixed_default":
		return 0.12
	case "mixed_rectangles", "mixed_ellipses":
		return 0.10
	default:
		return 0.0
	}
}

func shapeLabel(shapeType int) string {
	switch shapeType {
	case shapeRectangle:
		return "rectangle"
	case shapeRotRect:
		return "rotated rectangle"
	case shapeEllipse:
		return "ellipse"
	case shapeRotEllipse:
		return "rotated ellipse"
	default:
		return "shape"
	}
}

func clampInt(v, minV, maxV int) int {
	if v < minV {
		return minV
	}
	if v > maxV {
		return maxV
	}
	return v
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}
