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
upgrade that can simply be installed over the top of QIS Basic to turn it into QIS
Premium. Commercial support will only be offered to Premium users.

Other ways of implementing basic/premium modes - e.g. limiting the number of users,
limiting access to the API - are not really possible when the code is open source.
Anyone can just go into the code and disable the license checks.

### Imaging features

    | Feature                       | Pillow supports        | Support in QIS Basic
    -------------------------------------------------------------------------------
    | Read images from file, blob   | Y                      | Required
    | Ping image dimensions         | Y                      | Required for APIs
    | Read EXIF data                | Y                      |
    | Page selection (PDF,TIFF)     | Y                      |
    | Resize                        | Y                      |
    | Resize mode/quality           | Y                      |
    | Fit-to-size                   | Y (crop)               |
    | Border-image positioning      | Y (manual)             |
    | Rotation                      | Y                      |
    | Flip h and v                  | Y                      |
    | Cropping                      | Y                      |
    | Fill colour (resize, rotate)  | Y (manual)             |
    | Auto fill colour              | Y (Image.getpixel)     |
    | Format change                 | Y (formats below)      |
    | Compression setting           | Y (JPG and PNG)        |
    | Sharpen/blur                  | Y                      |
    | DPI change                    | ? (format dependent)   |
    | Strip EXIF, colour profiles   | Y (manual)             |
    | Overlays (size, transparency) | Y (manual)             |
    | ICC profile attach, apply     | Y (ImageCms module)    |
    | Colorspace conversion         | Y (Image.convert)      |
    | Tiling                        | Y (crop)               | Required for APIs

### qismagick special file handling

    | Feature                       | Pillow supports        | Support in QIS Basic
    -------------------------------------------------------------------------------
    | PDF to image                  | N (Y w/ghostscript)    |
    | Image to PDF                  | Y                      |
    | RAW reading                   | N                      | No (can't)

### Image format support

    | Feature                       | Pillow supports        | Support in QIS Basic
    -------------------------------------------------------------------------------
    | BMP rw                        | rw                     |
    | DCM rw                        | --                     |
    | GIF rw                        | rw                     |
    | EPS r-                        | rw                     |
    | JPG rw                        | rw                     | Required
    | PJPG rw                       | rw                     |
    | PDF rw                        | -w (rw w/ghostscript)  |
    | PNG rw                        | rw                     | Required
    | PPM rw                        | rw                     |
    | PSD rw                        | r-                     |
    | SVG rw                        | --                     | No (can't)
    | TGA rw                        | r-                     |
    | TIF rw                        | rw                     |
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
