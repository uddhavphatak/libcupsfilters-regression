### libcupsfilters regression: HEAD vs 2.1.1

| class | cases |
|---|---|
| CRASH | 0 |
| TIMEOUT | 1 |
| EXIT_DIFF | 0 |
| STRUCT_DIFF | 430 |
| VISUAL_DIFF | 409 |
| BOTH_FAIL | 114 |
| VISUAL_EQUAL | 1 |
| IDENTICAL | 96 |

**840 unexpected differences**

- `TIMEOUT` `pwg-pclm/test_file_4pg/default.pclm` candidate timed out
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_jpeg_color.jpg-4x6-sgray-8-300dpi.pwg/default.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_jpeg_color.jpg-4x6-sgray-8-300dpi.pwg/default.urf` unreadable output: unknown raster magic b'UNIR'
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_jpeg_color.jpg-4x6-sgray-8-300dpi.pwg/print-color-mode-monochrome.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_jpeg_color.jpg-4x6-srgb-8-300dpi.pwg/default.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_jpeg_color.jpg-4x6-srgb-8-300dpi.pwg/default.urf` unreadable output: unknown raster magic b'UNIR'
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_jpeg_color.jpg-4x6-srgb-8-300dpi.pwg/print-color-mode-monochrome.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_jpeg_onepage-a4-sgray-8-300dpi.pwg/default.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_jpeg_onepage-a4-sgray-8-300dpi.pwg/default.urf` unreadable output: unknown raster magic b'UNIR'
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_jpeg_onepage-a4-sgray-8-300dpi.pwg/print-color-mode-monochrome.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_jpeg_onepage-a4-srgb-8-300dpi.pwg/default.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_jpeg_onepage-a4-srgb-8-300dpi.pwg/default.urf` unreadable output: unknown raster magic b'UNIR'
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_jpeg_onepage-a4-srgb-8-300dpi.pwg/print-color-mode-monochrome.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_rle_color.jpg-4x6-sgray-8-300dpi.pwg/default.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_rle_color.jpg-4x6-sgray-8-300dpi.pwg/default.urf` unreadable output: unknown raster magic b'UNIR'
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_rle_color.jpg-4x6-sgray-8-300dpi.pwg/print-color-mode-monochrome.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_rle_color.jpg-4x6-srgb-8-300dpi.pwg/default.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_rle_color.jpg-4x6-srgb-8-300dpi.pwg/default.urf` unreadable output: unknown raster magic b'UNIR'
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_rle_color.jpg-4x6-srgb-8-300dpi.pwg/print-color-mode-monochrome.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_rle_onepage-a4-sgray-8-300dpi.pwg/default.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_rle_onepage-a4-sgray-8-300dpi.pwg/default.urf` unreadable output: unknown raster magic b'UNIR'
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_rle_onepage-a4-sgray-8-300dpi.pwg/print-color-mode-monochrome.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_rle_onepage-a4-srgb-8-300dpi.pwg/default.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_rle_onepage-a4-srgb-8-300dpi.pwg/default.urf` unreadable output: unknown raster magic b'UNIR'
- `STRUCT_DIFF` `pclmtoraster/16pixels_300dpi_rle_onepage-a4-srgb-8-300dpi.pwg/print-color-mode-monochrome.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_jpeg_color.jpg-4x6-sgray-8-600dpi.pwg/default.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_jpeg_color.jpg-4x6-sgray-8-600dpi.pwg/default.urf` unreadable output: unknown raster magic b'UNIR'
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_jpeg_color.jpg-4x6-sgray-8-600dpi.pwg/print-color-mode-monochrome.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_jpeg_color.jpg-4x6-srgb-8-600dpi.pwg/default.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_jpeg_color.jpg-4x6-srgb-8-600dpi.pwg/default.urf` unreadable output: unknown raster magic b'UNIR'
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_jpeg_color.jpg-4x6-srgb-8-600dpi.pwg/print-color-mode-monochrome.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_jpeg_onepage-a4-sgray-8-600dpi.pwg/default.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_jpeg_onepage-a4-sgray-8-600dpi.pwg/default.urf` unreadable output: unknown raster magic b'UNIR'
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_jpeg_onepage-a4-sgray-8-600dpi.pwg/print-color-mode-monochrome.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_jpeg_onepage-a4-srgb-8-600dpi.pwg/default.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_jpeg_onepage-a4-srgb-8-600dpi.pwg/default.urf` unreadable output: unknown raster magic b'UNIR'
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_jpeg_onepage-a4-srgb-8-600dpi.pwg/print-color-mode-monochrome.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_rle_color.jpg-4x6-sgray-8-600dpi.pwg/default.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_rle_color.jpg-4x6-sgray-8-600dpi.pwg/default.urf` unreadable output: unknown raster magic b'UNIR'
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_rle_color.jpg-4x6-sgray-8-600dpi.pwg/print-color-mode-monochrome.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_rle_color.jpg-4x6-srgb-8-600dpi.pwg/default.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_rle_color.jpg-4x6-srgb-8-600dpi.pwg/default.urf` unreadable output: unknown raster magic b'UNIR'
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_rle_color.jpg-4x6-srgb-8-600dpi.pwg/print-color-mode-monochrome.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_rle_onepage-a4-sgray-8-600dpi.pwg/default.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_rle_onepage-a4-sgray-8-600dpi.pwg/default.urf` unreadable output: unknown raster magic b'UNIR'
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_rle_onepage-a4-sgray-8-600dpi.pwg/print-color-mode-monochrome.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_rle_onepage-a4-srgb-8-600dpi.pwg/default.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_rle_onepage-a4-srgb-8-600dpi.pwg/default.urf` unreadable output: unknown raster magic b'UNIR'
- `STRUCT_DIFF` `pclmtoraster/16pixels_600dpi_rle_onepage-a4-srgb-8-600dpi.pwg/print-color-mode-monochrome.pwg` page count 1 -> 0
- `STRUCT_DIFF` `pclmtoraster/32pixels_300dpi_jpeg_color.jpg-4x6-sgray-8-300dpi.pwg/default.pwg` page count 1 -> 0
- ... and 790 more (see report.html)
