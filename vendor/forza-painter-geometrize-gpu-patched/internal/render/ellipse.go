package render

import (
	"image"
	"image/color"
	"image/png"
	"math"
	"os"

	"forza-painter-geometrize-go/internal/model"
)

func ApplyEllipse(dst []float32, mask []uint8, width, height int, c model.Candidate) {
	if c.RX < 1 {
		c.RX = 1
	}
	if c.RY < 1 {
		c.RY = 1
	}
	t := c.Theta * (math.Pi / 180.0)
	cosT := float32(math.Cos(float64(t)))
	sinT := float32(math.Sin(float64(t)))
	invRX2 := float32(1.0) / (c.RX * c.RX)
	invRY2 := float32(1.0) / (c.RY * c.RY)

	xMin := clampInt(int(c.X-c.RX-1), 0, width-1)
	xMax := clampInt(int(c.X+c.RX+1), 0, width-1)
	yMin := clampInt(int(c.Y-c.RY-1), 0, height-1)
	yMax := clampInt(int(c.Y+c.RY+1), 0, height-1)

	for y := yMin; y <= yMax; y++ {
		for x := xMin; x <= xMax; x++ {
			if mask[y*width+x] == 0 {
				continue
			}
			dx := float32(x) + 0.5 - c.X
			dy := float32(y) + 0.5 - c.Y
			xr := dx*cosT + dy*sinT
			yr := -dx*sinT + dy*cosT
			inside := xr*xr*invRX2+yr*yr*invRY2 <= 1.0
			if !inside {
				continue
			}
			idx := (y*width + x) * 4
			alpha := c.A
			inv := 1.0 - alpha
			dst[idx+0] = dst[idx+0]*inv + c.R*alpha
			dst[idx+1] = dst[idx+1]*inv + c.G*alpha
			dst[idx+2] = dst[idx+2]*inv + c.B*alpha
			dst[idx+3] = dst[idx+3]*inv + alpha
		}
	}
}

func SavePNG(path string, pix []float32, width, height int) error {
	img := image.NewRGBA(image.Rect(0, 0, width, height))
	for y := 0; y < height; y++ {
		for x := 0; x < width; x++ {
			idx := (y*width + x) * 4
			img.SetRGBA(x, y, color.RGBA{
				R: toByte(pix[idx+0]),
				G: toByte(pix[idx+1]),
				B: toByte(pix[idx+2]),
				A: toByte(pix[idx+3]),
			})
		}
	}
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	return png.Encode(f, img)
}

func SaveShapePreviewPNG(path string, shapes []model.Shape, width, height int) error {
	img := image.NewRGBA(image.Rect(0, 0, width, height))

	bgA := 0
	if len(shapes) > 0 && shapes[0].Type == 1 && len(shapes[0].Color) >= 4 {
		bg := shapes[0].Color
		bgA = bg[3]
		if bgA > 0 {
			fillRGBA(img, color.RGBA{R: uint8(bg[0]), G: uint8(bg[1]), B: uint8(bg[2]), A: 255})
		}
	}
	if bgA <= 0 {
		fillCheckerboard(img)
	}

	for i, s := range shapes {
		if i == 0 {
			continue
		}
		if len(s.Color) < 4 || s.Color[3] <= 0 || len(s.Data) < 4 {
			continue
		}
		c := color.RGBA{R: uint8(s.Color[0]), G: uint8(s.Color[1]), B: uint8(s.Color[2]), A: 255}
		switch s.Type {
		case 1:
			cx, cy := s.Data[0], s.Data[1]
			w, h := s.Data[2], s.Data[3]
			x0 := int(math.Round(float64(cx) - float64(w)/2.0))
			y0 := int(math.Round(float64(cy) - float64(h)/2.0))
			x1 := int(math.Round(float64(cx) + float64(w)/2.0))
			y1 := int(math.Round(float64(cy) + float64(h)/2.0))
			fillRect(img, x0, y0, x1, y1, c)
		case 16:
			cx := float32(s.Data[0])
			cy := float32(s.Data[1])
			rx := float32(maxInt(1, s.Data[2]))
			ry := float32(maxInt(1, s.Data[3]))
			theta := float32(0)
			if len(s.Data) >= 5 {
				theta = float32(s.Data[4])
			}
			adjW, adjH := compensatedEllipseSize(float64(rx), float64(ry))
			cand := model.Candidate{
				Type: 16,
				X:    cx,
				Y:    cy,
				RX:   float32(adjH),
				RY:   float32(adjW),
				Theta: normalizePreviewTheta(theta),
				R:    float32(c.R) / 255.0,
				G:    float32(c.G) / 255.0,
				B:    float32(c.B) / 255.0,
				A:    1.0,
			}
			applyEllipseSolid(img, cand)
		}
	}

	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	return png.Encode(f, img)
}

func fillRGBA(img *image.RGBA, c color.RGBA) {
	b := img.Bounds()
	for y := b.Min.Y; y < b.Max.Y; y++ {
		for x := b.Min.X; x < b.Max.X; x++ {
			img.SetRGBA(x, y, c)
		}
	}
}

func fillCheckerboard(img *image.RGBA) {
	b := img.Bounds()
	const tile = 32
	c0 := color.RGBA{R: 58, G: 58, B: 58, A: 255}
	c1 := color.RGBA{R: 38, G: 38, B: 38, A: 255}
	for y := b.Min.Y; y < b.Max.Y; y++ {
		for x := b.Min.X; x < b.Max.X; x++ {
			if ((x/tile)+(y/tile))%2 == 0 {
				img.SetRGBA(x, y, c0)
			} else {
				img.SetRGBA(x, y, c1)
			}
		}
	}
}

func fillRect(img *image.RGBA, x0, y0, x1, y1 int, c color.RGBA) {
	b := img.Bounds()
	if x0 > x1 {
		x0, x1 = x1, x0
	}
	if y0 > y1 {
		y0, y1 = y1, y0
	}
	if x0 < b.Min.X {
		x0 = b.Min.X
	}
	if y0 < b.Min.Y {
		y0 = b.Min.Y
	}
	if x1 >= b.Max.X {
		x1 = b.Max.X - 1
	}
	if y1 >= b.Max.Y {
		y1 = b.Max.Y - 1
	}
	for y := y0; y <= y1; y++ {
		for x := x0; x <= x1; x++ {
			img.SetRGBA(x, y, c)
		}
	}
}

func applyEllipseSolid(img *image.RGBA, c model.Candidate) {
	if c.RX < 1 {
		c.RX = 1
	}
	if c.RY < 1 {
		c.RY = 1
	}
	t := c.Theta * (math.Pi / 180.0)
	cosT := float32(math.Cos(float64(t)))
	sinT := float32(math.Sin(float64(t)))
	invRX2 := float32(1.0) / (c.RX * c.RX)
	invRY2 := float32(1.0) / (c.RY * c.RY)
	b := img.Bounds()
	xMin := clampInt(int(c.X-c.RX-1), b.Min.X, b.Max.X-1)
	xMax := clampInt(int(c.X+c.RX+1), b.Min.X, b.Max.X-1)
	yMin := clampInt(int(c.Y-c.RY-1), b.Min.Y, b.Max.Y-1)
	yMax := clampInt(int(c.Y+c.RY+1), b.Min.Y, b.Max.Y-1)
	fill := color.RGBA{
		R: toByte(c.R),
		G: toByte(c.G),
		B: toByte(c.B),
		A: 255,
	}
	for y := yMin; y <= yMax; y++ {
		for x := xMin; x <= xMax; x++ {
			dx := float32(x) + 0.5 - c.X
			dy := float32(y) + 0.5 - c.Y
			xr := dx*cosT + dy*sinT
			yr := -dx*sinT + dy*cosT
			if xr*xr*invRX2+yr*yr*invRY2 <= 1.0 {
				img.SetRGBA(x, y, fill)
			}
		}
	}
}

func normalizePreviewTheta(theta float32) float32 {
	angle := theta - 90.0
	for angle < 0 {
		angle += 360
	}
	for angle >= 360 {
		angle -= 360
	}
	return angle
}

func compensatedEllipseSize(w, h float64) (float64, float64) {
	major := math.Max(w, h)
	minor := math.Max(1.0, math.Min(w, h))
	aspect := major / minor

	uniformScale := 1.0
	if major >= 220 {
		uniformScale *= 0.985
	}
	if major >= 300 {
		uniformScale *= 0.975
	}

	majorAxisScale := 1.0
	if aspect >= 2.0 {
		majorAxisScale *= 0.985
	}
	if aspect >= 3.5 {
		majorAxisScale *= 0.970
	}
	if aspect >= 6.0 {
		majorAxisScale *= 0.955
	}

	var sx, sy float64
	if w >= h {
		sx = uniformScale * majorAxisScale
		sy = uniformScale
	} else {
		sx = uniformScale
		sy = uniformScale * majorAxisScale
	}

	return math.Max(1.0, w*sx), math.Max(1.0, h*sy)
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func toByte(v float32) uint8 {
	if v < 0 {
		v = 0
	}
	if v > 1 {
		v = 1
	}
	return uint8(math.Round(float64(v * 255)))
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
