# Implementing a Pillow back-end

Currently most of QIS is open source on GitHub, but the crucial `qismagick` C library
for interfacing with ImageMagick is not. This means that in open source mode alone,
QIS does not run.

In recent discussions it has been agreed that QIS should be able to run "out of the
box". The proposed approach is to implement a basic cut-down imaging library based
on Pillow (https://github.com/python-pillow/Pillow) that provides image resizing
and other basic features (see below) as standard.

This new "basic" mode means that the open source version of QIS will now be
functional, and so will hopefully attract new users to try it out. The existing
`qismagick` library, which offers full imaging functionality, will become a paid-for
upgrade that can simply be installed over the top to turn QIS into "premium" mode.
Commercial support will only be offered to premium users.

Other ways of implementing basic/premium modes - e.g. limiting the number of users,
limiting access to the API - are not really possible when the code is open source.
Anyone can just go into the code and disable the license checks.

### Imaging features

    | Feature                       | Pillow supports        | Support in QIS Basic
    -------------------------------------------------------------------------------
    | Read images from file, blob   | Y                      | P1 required
    | Ping image dimensions         | Y                      | P1 required for APIs
    | Read EXIF data                | Y                      | P1
    | Page selection (PDF,TIFF)     | Y                      | P3
    | Resize                        | Y                      | P1
    | Resize mode/quality           | Y                      | P2
    | Fit-to-size                   | Y (crop)               | P1
    | Border-image positioning      | Y (manual)             | P3
    | Rotation                      | Y                      | P1
    | Flip h and v                  | Y                      | P1
    | Cropping                      | Y                      | P1
    | Fill colour (resize, rotate)  | Y (manual)             | P2
    | Auto fill colour              | Y (Image.getpixel)     | P3
    | Format change                 | Y (formats below)      | P1 selected formats
    | Compression setting           | Y (JPG and PNG)        | P1
    | Sharpen/blur                  | Y                      | P2
    | DPI change                    | ? (format dependent)   | P3
    | Strip EXIF, colour profiles   | Y (manual)             | P1
    | Overlays (size, transparency) | Y (manual)             | P2
    | ICC profile attach, apply     | Y (ImageCms module)    | P3
    | Colorspace conversion         | Y (Image.convert)      | P3
    | Tiling                        | Y (crop)               | P1 required for APIs

### qismagick special file handling

    | Feature                       | Pillow supports        | Support in QIS Basic
    -------------------------------------------------------------------------------
    | PDF to image                  | N (Y w/ghostscript)    | P3
    | Image to PDF                  | Y                      | No
    | RAW reading                   | N                      | No (can't)

### Image format support

    | Feature                       | Pillow supports        | Support in QIS Basic
    -------------------------------------------------------------------------------
    | BMP rw                        | rw                     | No
    | DCM rw                        | --                     | No
    | GIF rw                        | rw                     | P1
    | EPS r-                        | rw                     | No
    | JPG rw                        | rw                     | P1 required
    | PJPG rw                       | rw                     | P3
    | PDF rw                        | -w (rw w/ghostscript)  | P3 r-
    | PNG rw                        | rw                     | P1 required
    | PPM rw                        | rw                     | No
    | PSD rw                        | r-                     | No
    | SVG rw                        | --                     | No (can't)
    | TGA rw                        | r-                     | No
    | TIF rw                        | rw                     | P1
    | XCF rw                        | --                     | No (can't)
    | RAW (various) r-              | --                     | No (can't)

### Pillow notes

* No SVG file support
  https://github.com/python-pillow/Pillow/issues/1146
* No RAW file support
  https://github.com/python-pillow/Pillow/issues/3124
* Saved GIF files are too large (we should test JPG, PNG)
  https://github.com/python-pillow/Pillow/issues/617
* Converting a JPG to CMYK and saving it loses EXIF data
  https://github.com/python-pillow/Pillow/issues/1676
* Files with bad EXIF data do not open in Pillow (but do in ImageMagick)
  https://github.com/python-pillow/Pillow/issues/518
* Stripping EXIF data from an image
  https://stackoverflow.com/a/23249933/1671320

### Pillow limitations vs ImageMagick/qismagick

* No RAW file support
* No SVG file support
* Fewer other/legacy file types supported
* Worse PDF support
* No PNG filter type control
* No support for more than 8 bpp / 32 bit color (ImageMagick uses 16 bpp
  by default so that e.g. colorspace conversions do not cause clipping)
* Loss of some metadata even with strip=0
* Loss of some embedded colour profiles (suspected, awaiting tests)
* Slow gamma corrected resizing (or, choose no gamma correction)
