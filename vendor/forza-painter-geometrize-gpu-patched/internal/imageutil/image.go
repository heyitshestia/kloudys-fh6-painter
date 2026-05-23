package imageutil

import (
	"fmt"
	"image"
	_ "image/jpeg"
	_ "image/png"
	"math"
	"os"

	"golang.org/x/image/draw"
)

type PreparedImage struct {
	Width           int
	Height          int
	Target          []float32
	ScoringTarget   []float32
	Current         []float32
	OpaqueMask      []uint8
	HasTransparency bool
	BackgroundRGBA  [4]uint8
}

const opaqueAlphaThreshold = 8.0 / 255.0

func LoadAndPrepare(path string, maxResolution int, detailMode string) (*PreparedImage, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	src, _, err := image.Decode(f)
	if err != nil {
		return nil, err
	}

	scaled := resizeToMax(src, maxResolution)
	bounds := scaled.Bounds()
	w := bounds.Dx()
	h := bounds.Dy()
	if w <= 0 || h <= 0 {
		return nil, fmt.Errorf("invalid image size")
	}

	target := make([]float32, w*h*4)
	current := make([]float32, w*h*4)
	mask := make([]uint8, w*h)

	var sumR, sumG, sumB, sumA float64
	var opaqueCount float64
	hasTransparency := false

	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			r16, g16, b16, a16 := scaled.At(bounds.Min.X+x, bounds.Min.Y+y).RGBA()
			r := float32(r16) / 65535.0
			g := float32(g16) / 65535.0
			b := float32(b16) / 65535.0
			a := float32(a16) / 65535.0

			idx := (y*w + x) * 4
			target[idx+0] = r
			target[idx+1] = g
			target[idx+2] = b
			target[idx+3] = a

			// Treat very low alpha as transparent so tiny holes and
			// anti-aliased cutouts stay protected from shape overhang.
			if a >= opaqueAlphaThreshold {
				mask[y*w+x] = 1
				sumR += float64(r)
				sumG += float64(g)
				sumB += float64(b)
				sumA += float64(a)
				opaqueCount++
			} else {
				hasTransparency = true
			}
		}
	}

	bg := [4]uint8{0, 0, 0, 255}
	if opaqueCount > 0 {
		bg[0] = uint8(clamp255(sumR / opaqueCount * 255.0))
		bg[1] = uint8(clamp255(sumG / opaqueCount * 255.0))
		bg[2] = uint8(clamp255(sumB / opaqueCount * 255.0))
		bg[3] = uint8(clamp255(sumA / opaqueCount * 255.0))
	}
	if hasTransparency {
		// Transparent source: drive bg.alpha to 0 so the FH6 importer
		// skips writing a background rectangle (transparent regions stay
		// truly transparent in-game and reveal whatever color the user
		// has painted the car body with).
		//
		// We deliberately keep the *RGB* equal to the average opaque
		// color rather than the legacy [255,0,255] magenta marker. The
		// FH6 importer still uses these RGB bytes for two things even
		// when alpha is 0:
		//   1. The "ideal background color for the car" advice it
		//      prints on import — so the user paints the car with a
		//      color that blends with the visible content instead of
		//      with a hard-coded magenta.
		//   2. The Selected-JSON preview panel, which fills the canvas
		//      with the bg RGB ignoring alpha; using the average color
		//      makes that preview look like a coherent image instead of
		//      a magenta plate.
		// Both downstream uses are now sensible while the actual import
		// behavior (skip the bg rectangle) is unchanged.
		bg[3] = 0
	}

	for i := 0; i < len(current); i += 4 {
		if hasTransparency {
			current[i+0] = 0
			current[i+1] = 0
			current[i+2] = 0
			current[i+3] = 0
		} else {
			current[i+0] = float32(bg[0]) / 255.0
			current[i+1] = float32(bg[1]) / 255.0
			current[i+2] = float32(bg[2]) / 255.0
			current[i+3] = 1.0
		}
	}

	scoringTarget := target
	switch detailMode {
	case "coarse_first":
		scoringTarget = makeCoarseScoringTarget(target, w, h, 2, 0.75)
	case "coarse_balanced":
		scoringTarget = makeCoarseScoringTarget(target, w, h, 3, 0.82)
	case "coarse_strict":
		scoringTarget = makeCoarseScoringTarget(target, w, h, 4, 0.90)
	}

	return &PreparedImage{
		Width:           w,
		Height:          h,
		Target:          target,
		ScoringTarget:   scoringTarget,
		Current:         current,
		OpaqueMask:      mask,
		HasTransparency: hasTransparency,
		BackgroundRGBA:  bg,
	}, nil
}

func resizeToMax(src image.Image, maxResolution int) image.Image {
	if maxResolution <= 0 {
		return src
	}
	bounds := src.Bounds()
	w := bounds.Dx()
	h := bounds.Dy()
	maxDim := w
	if h > maxDim {
		maxDim = h
	}
	if maxDim <= maxResolution {
		return src
	}

	scale := float64(maxResolution) / float64(maxDim)
	nw := int(math.Round(float64(w) * scale))
	nh := int(math.Round(float64(h) * scale))
	if nw < 1 {
		nw = 1
	}
	if nh < 1 {
		nh = 1
	}
	dst := image.NewRGBA(image.Rect(0, 0, nw, nh))
	draw.CatmullRom.Scale(dst, dst.Bounds(), src, bounds, draw.Over, nil)
	return dst
}

func clamp255(v float64) float64 {
	if v < 0 {
		return 0
	}
	if v > 255 {
		return 255
	}
	return v
}

func makeCoarseScoringTarget(src []float32, width, height, radius int, blurWeight float32) []float32 {
	if radius <= 0 || blurWeight <= 0 {
		out := make([]float32, len(src))
		copy(out, src)
		return out
	}
	if blurWeight > 1 {
		blurWeight = 1
	}
	blurred := boxBlurRGBA(src, width, height, radius)
	out := make([]float32, len(src))
	origWeight := 1 - blurWeight
	for i := range src {
		out[i] = src[i]*origWeight + blurred[i]*blurWeight
	}
	return out
}

func boxBlurRGBA(src []float32, width, height, radius int) []float32 {
	if radius <= 0 {
		out := make([]float32, len(src))
		copy(out, src)
		return out
	}
	tmp := make([]float32, len(src))
	out := make([]float32, len(src))

	for y := 0; y < height; y++ {
		for x := 0; x < width; x++ {
			x0 := x - radius
			if x0 < 0 {
				x0 = 0
			}
			x1 := x + radius
			if x1 >= width {
				x1 = width - 1
			}
			count := float32(x1 - x0 + 1)
			for c := 0; c < 4; c++ {
				sum := float32(0)
				for xx := x0; xx <= x1; xx++ {
					sum += src[(y*width+xx)*4+c]
				}
				tmp[(y*width+x)*4+c] = sum / count
			}
		}
	}

	for y := 0; y < height; y++ {
		y0 := y - radius
		if y0 < 0 {
			y0 = 0
		}
		y1 := y + radius
		if y1 >= height {
			y1 = height - 1
		}
		count := float32(y1 - y0 + 1)
		for x := 0; x < width; x++ {
			for c := 0; c < 4; c++ {
				sum := float32(0)
				for yy := y0; yy <= y1; yy++ {
					sum += tmp[(yy*width+x)*4+c]
				}
				out[(y*width+x)*4+c] = sum / count
			}
		}
	}

	return out
}
