//
// Differential-testing harness for libcupsfilters.
//
// Runs exactly one filter job through the public libcupsfilters API so the
// same source can be compiled against any installed libcupsfilters 2.x and
// its output compared across builds.  Derived from cupsfilters/testfilters.c.
//
// Copyright 2026 Uddhav Phatak <uddhavphatak@gmail.com>
//
// Licensed under Apache License v2.0.  See the file "LICENSE" for more
// information.
//

#include <cupsfilters/filter.h>
#include <cups/cups.h>
#include <cups/array.h>
#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <unistd.h>

#if CUPS_VERSION_MAJOR < 3
#  define cupsArrayGetCount cupsArrayCount
#  define cupsArrayGetFirst cupsArrayFirst
#  define cupsArrayGetNext  cupsArrayNext
#  define cupsArrayNew      cupsArrayNew3
#  define cupsParseOptions(arg, end, num_options, options) cupsParseOptions(arg, num_options, options)
#endif


typedef struct
{
  const char *out_mime;
  const char *banner_dir;
  cf_filter_texttopdf_parameter_t texttopdf;
} param_ctx_t;

typedef void *(*param_gen_t)(const param_ctx_t *ctx);

typedef struct
{
  const char           *name;
  cf_filter_function_t function;
  param_gen_t          params;
} filter_map_t;


static void *
out_format_param(const param_ctx_t *ctx)
{
  cf_filter_out_format_t *out = malloc(sizeof(cf_filter_out_format_t));

  if (!strcasecmp(ctx->out_mime, "application/pdf"))
    *out = CF_FILTER_OUT_FORMAT_PDF;
  else if (!strcasecmp(ctx->out_mime, "application/PCLm"))
    *out = CF_FILTER_OUT_FORMAT_PCLM;
  else if (!strcasecmp(ctx->out_mime, "image/pwg-raster"))
    *out = CF_FILTER_OUT_FORMAT_PWG_RASTER;
  else if (!strcasecmp(ctx->out_mime, "image/urf"))
    *out = CF_FILTER_OUT_FORMAT_APPLE_RASTER;
  else if (!strcasecmp(ctx->out_mime, "application/vnd.cups-raster"))
    *out = CF_FILTER_OUT_FORMAT_CUPS_RASTER;
  else
  {
    free(out);
    return (NULL);
  }

  return (out);
}

static void *
banner_param(const param_ctx_t *ctx)
{
  return (ctx->banner_dir ? strdup(ctx->banner_dir) : NULL);
}

static void *
texttopdf_param(const param_ctx_t *ctx)
{
  cf_filter_texttopdf_parameter_t *p = malloc(sizeof(*p));

  *p = ctx->texttopdf;
  return (p);
}

static const filter_map_t filters[] =
{
  { "bannertopdf",   cfFilterBannerToPDF,   banner_param },
  { "ghostscript",   cfFilterGhostscript,   out_format_param },
  { "imagetopdf",    cfFilterImageToPDF,    NULL },
  { "imagetoraster", cfFilterImageToRaster, NULL },
  { "mupdftopwg",    cfFilterMuPDFToPWG,    NULL },
  { "pclmtoraster",  cfFilterPCLmToRaster,  out_format_param },
  { "pdftopdf",      cfFilterPDFToPDF,      NULL },
  { "pdftoraster",   cfFilterPDFToRaster,   NULL },
  { "pwgtopdf",      cfFilterPWGToPDF,      out_format_param },
  { "pwgtoraster",   cfFilterPWGToRaster,   NULL },
  { "rastertopwg",   cfFilterRasterToPWG,   NULL },
  { "texttopdf",     cfFilterTextToPDF,     texttopdf_param },
  { "texttotext",    cfFilterTextToText,    NULL },
};


static cups_array_t *
parse_chain(char *spec, const param_ctx_t *ctx)
{
  cups_array_t *chain = cupsArrayNew(NULL, NULL, NULL, 0, NULL, NULL);
  char         *save = NULL, *name;
  size_t       i;

  for (name = strtok_r(spec, ",", &save); name; name = strtok_r(NULL, ",", &save))
  {
    for (i = 0; i < sizeof(filters) / sizeof(filters[0]); i ++)
      if (!strcasecmp(name, filters[i].name))
        break;

    if (i >= sizeof(filters) / sizeof(filters[0]))
    {
      fprintf(stderr, "harness: unknown filter \"%s\"\n", name);
      exit(2);
    }

    cf_filter_filter_in_chain_t *f = calloc(1, sizeof(*f));
    f->function   = filters[i].function;
    f->name       = (char *)filters[i].name;
    f->parameters = filters[i].params ? filters[i].params(ctx) : NULL;
    cupsArrayAdd(chain, f);
  }

  return (chain);
}


static ipp_t *
media_col(const char *pwg_name, int bottom, int left, int right, int top)
{
  pwg_media_t *pwg = pwgMediaForPWG(pwg_name);
  ipp_t       *col = ippNew(), *size = ippNew();

  ippAddInteger(size, IPP_TAG_ZERO, IPP_TAG_INTEGER, "x-dimension", pwg->width);
  ippAddInteger(size, IPP_TAG_ZERO, IPP_TAG_INTEGER, "y-dimension", pwg->length);
  ippAddCollection(col, IPP_TAG_PRINTER, "media-size", size);
  ippDelete(size);
  ippAddString(col, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "media-size-name", NULL, pwg_name);
  ippAddInteger(col, IPP_TAG_PRINTER, IPP_TAG_INTEGER, "media-bottom-margin", bottom);
  ippAddInteger(col, IPP_TAG_PRINTER, IPP_TAG_INTEGER, "media-left-margin", left);
  ippAddInteger(col, IPP_TAG_PRINTER, IPP_TAG_INTEGER, "media-right-margin", right);
  ippAddInteger(col, IPP_TAG_PRINTER, IPP_TAG_INTEGER, "media-top-margin", top);

  return (col);
}


//
// Fixed emulated IPP Everywhere printer; identical for both builds so any
// output difference comes from libcupsfilters itself.
//

static ipp_t *
printer_attrs(int color, int duplex, const char *default_media)
{
  static const char * const media[] =
  {
    "na_letter_8.5x11in", "na_legal_8.5x14in", "iso_a4_210x297mm",
    "iso_a5_148x210mm", "iso_a3_297x420mm", "na_index-4x6_4x6in"
  };
  static const char * const sides[] = { "one-sided", "two-sided-long-edge", "two-sided-short-edge" };
  static const char * const color_modes[] = { "auto", "color", "monochrome" };
  static const char * const pwg_types_color[] = { "black_1", "sgray_8", "srgb_8" };
  static const char * const pwg_types_mono[] = { "black_1", "sgray_8" };
  static const char * const urf_color[] = { "CP1", "IS1-4-5-7-19", "MT1-2-3-4-5", "RS300-600", "SRGB24", "V1.4", "W8", "DM3" };
  static const char * const urf_mono[] = { "CP1", "IS1-4-5-19", "MT1-2-3-4-5", "RS300-600", "V1.4", "W8", "DM1" };
  static const char * const formats[] =
  {
    "application/pdf", "application/PCLm", "image/pwg-raster", "image/urf",
    "image/jpeg", "image/png", "text/plain"
  };
  static const int orient[] = { IPP_ORIENT_PORTRAIT, IPP_ORIENT_LANDSCAPE, IPP_ORIENT_REVERSE_LANDSCAPE, IPP_ORIENT_REVERSE_PORTRAIT };
  static const int quality[] = { IPP_QUALITY_DRAFT, IPP_QUALITY_NORMAL, IPP_QUALITY_HIGH };
  static const int res[] = { 300, 600 };

  ipp_t           *attrs = ippNew(), *col;
  ipp_attribute_t *attr = NULL;
  size_t          i, nmedia = sizeof(media) / sizeof(media[0]);

  ippAddString(attrs, IPP_TAG_PRINTER, IPP_TAG_TEXT, "printer-make-and-model", NULL, "Regression Harness");
  ippAddString(attrs, IPP_TAG_PRINTER, IPP_TAG_TEXT, "printer-device-id", NULL, "MFG:Regression;MDL:Harness;CMD:PDF,PWG,URF;");
  ippAddBoolean(attrs, IPP_TAG_PRINTER, "color-supported", (char)color);
  ippAddRange(attrs, IPP_TAG_PRINTER, "copies-supported", 1, 999);
  ippAddInteger(attrs, IPP_TAG_PRINTER, IPP_TAG_INTEGER, "copies-default", 1);
  ippAddBoolean(attrs, IPP_TAG_PRINTER, "page-ranges-supported", 1);
  ippAddStrings(attrs, IPP_TAG_PRINTER, IPP_TAG_MIMETYPE, "document-format-supported", (int)(sizeof(formats) / sizeof(formats[0])), NULL, formats);

  for (i = 0; i < nmedia; i ++)
  {
    int lr = strstr(media[i], "a4") ? 340 : 635;

    col = media_col(media[i], 635, lr, lr, 635);
    if (attr)
      ippSetCollection(attrs, &attr, ippGetCount(attr), col);
    else
      attr = ippAddCollection(attrs, IPP_TAG_PRINTER, "media-col-database", col);
    ippDelete(col);
  }

  col = media_col(default_media, 635, strstr(default_media, "a4") ? 340 : 635, strstr(default_media, "a4") ? 340 : 635, 635);
  ippAddCollection(attrs, IPP_TAG_PRINTER, "media-col-default", col);
  ippAddCollection(attrs, IPP_TAG_PRINTER, "media-col-ready", col);
  ippDelete(col);
  ippAddString(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "media-default", NULL, default_media);
  ippAddString(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "media-ready", NULL, default_media);
  ippAddStrings(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "media-supported", (int)nmedia, NULL, media);

  ippAddIntegers(attrs, IPP_TAG_PRINTER, IPP_TAG_ENUM, "orientation-requested-supported", 4, orient);
  ippAddInteger(attrs, IPP_TAG_PRINTER, IPP_TAG_ENUM, "orientation-requested-default", IPP_ORIENT_PORTRAIT);
  ippAddString(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "output-bin-default", NULL, "face-down");
  ippAddString(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "output-bin-supported", NULL, "face-down");

  ippAddString(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "print-color-mode-default", NULL, color ? "auto" : "monochrome");
  if (color)
    ippAddStrings(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "print-color-mode-supported", 3, NULL, color_modes);
  else
    ippAddString(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "print-color-mode-supported", NULL, "monochrome");

  ippAddInteger(attrs, IPP_TAG_PRINTER, IPP_TAG_ENUM, "print-quality-default", IPP_QUALITY_NORMAL);
  ippAddIntegers(attrs, IPP_TAG_PRINTER, IPP_TAG_ENUM, "print-quality-supported", 3, quality);

  ippAddResolution(attrs, IPP_TAG_PRINTER, "printer-resolution-default", IPP_RES_PER_INCH, 300, 300);
  ippAddResolutions(attrs, IPP_TAG_PRINTER, "printer-resolution-supported", 2, IPP_RES_PER_INCH, res, res);
  ippAddResolutions(attrs, IPP_TAG_PRINTER, "pwg-raster-document-resolution-supported", 2, IPP_RES_PER_INCH, res, res);
  if (color)
    ippAddStrings(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "pwg-raster-document-type-supported", 3, NULL, pwg_types_color);
  else
    ippAddStrings(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "pwg-raster-document-type-supported", 2, NULL, pwg_types_mono);

  ippAddResolution(attrs, IPP_TAG_PRINTER, "pclm-source-resolution-default", IPP_RES_PER_INCH, 300, 300);
  ippAddResolutions(attrs, IPP_TAG_PRINTER, "pclm-source-resolution-supported", 2, IPP_RES_PER_INCH, res, res);
  ippAddInteger(attrs, IPP_TAG_PRINTER, IPP_TAG_INTEGER, "pclm-strip-height-preferred", 16);
  ippAddInteger(attrs, IPP_TAG_PRINTER, IPP_TAG_INTEGER, "pclm-strip-height-supported", 16);
  ippAddString(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "pclm-compression-method-preferred", NULL, "flate");
  if (duplex)
    ippAddString(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "pclm-raster-back-side", NULL, "rotated");

  if (color)
    ippAddStrings(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "urf-supported", duplex ? 8 : 7, NULL, urf_color);
  else
    ippAddStrings(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "urf-supported", duplex ? 7 : 6, NULL, urf_mono);

  ippAddString(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "sides-default", NULL, "one-sided");
  if (duplex)
  {
    ippAddStrings(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "sides-supported", 3, NULL, sides);
    ippAddString(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "pwg-raster-document-sheet-back", NULL, color ? "rotated" : "normal");
  }
  else
    ippAddString(attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD, "sides-supported", NULL, "one-sided");

  return (attrs);
}


static void
usage(void)
{
  fputs("usage: harness --in FILE --in-type MIME --out FILE --out-type MIME\n"
        "               [--chain f1,f2,...] [--options \"k=v ...\"] [--copies N]\n"
        "               [--color 0|1] [--duplex 0|1] [--media PWGNAME]\n"
        "               [--banner-dir DIR] [--data-dir DIR]\n", stderr);
  exit(2);
}


int
main(int argc, char *argv[])
{
  static const struct option longopts[] =
  {
    { "in",         required_argument, NULL, 'i' },
    { "in-type",    required_argument, NULL, 'I' },
    { "out",        required_argument, NULL, 'o' },
    { "out-type",   required_argument, NULL, 'O' },
    { "chain",      required_argument, NULL, 'c' },
    { "options",    required_argument, NULL, 'p' },
    { "copies",     required_argument, NULL, 'n' },
    { "color",      required_argument, NULL, 'C' },
    { "duplex",     required_argument, NULL, 'D' },
    { "media",      required_argument, NULL, 'm' },
    { "banner-dir", required_argument, NULL, 'b' },
    { "data-dir",   required_argument, NULL, 'd' },
    { NULL, 0, NULL, 0 }
  };
  const char       *in = NULL, *in_type = NULL, *out = NULL, *out_type = NULL;
  const char       *optstr = NULL, *media = "iso_a4_210x297mm", *fontpath;
  char             *chain_spec = NULL;
  int              copies = 1, color = 1, duplex = 1, ch, inputfd, outputfd, ret;
  int              canceled = 0;
  param_ctx_t      ctx;
  cf_filter_data_t data;
  cups_array_t     *chain = NULL;
  cf_filter_filter_in_chain_t *f;

  memset(&ctx, 0, sizeof(ctx));
  ctx.banner_dir = getenv("HARNESS_BANNER_DIR");
  ctx.texttopdf.data_dir = getenv("CUPS_DATADIR");

  while ((ch = getopt_long(argc, argv, "", longopts, NULL)) != -1)
  {
    switch (ch)
    {
      case 'i' : in = optarg; break;
      case 'I' : in_type = optarg; break;
      case 'o' : out = optarg; break;
      case 'O' : out_type = optarg; break;
      case 'c' : chain_spec = strdup(optarg); break;
      case 'p' : optstr = optarg; break;
      case 'n' : copies = atoi(optarg); break;
      case 'C' : color = atoi(optarg); break;
      case 'D' : duplex = atoi(optarg); break;
      case 'm' : media = optarg; break;
      case 'b' : ctx.banner_dir = optarg; break;
      case 'd' : ctx.texttopdf.data_dir = optarg; break;
      default  : usage();
    }
  }

  if (!in || !in_type || !out || !out_type)
    usage();

  ctx.out_mime = out_type;

  setbuf(stderr, NULL);
  signal(SIGPIPE, SIG_IGN);

  if ((inputfd = open(in, O_RDONLY)) < 0)
  {
    fprintf(stderr, "harness: unable to open \"%s\": %s\n", in, strerror(errno));
    return (2);
  }

  if ((outputfd = open(out, O_WRONLY | O_CREAT | O_TRUNC, 0644)) < 0)
  {
    fprintf(stderr, "harness: unable to create \"%s\": %s\n", out, strerror(errno));
    close(inputfd);
    return (2);
  }

  memset(&data, 0, sizeof(data));
  data.printer            = "regression";
  data.job_id             = 1;
  data.job_user           = "regression";
  data.job_title          = "regression";
  data.copies             = copies;
  data.content_type       = (char *)in_type;
  data.final_content_type = (char *)out_type;
  data.printer_attrs      = printer_attrs(color, duplex, media);
  data.back_pipe[0]       = data.back_pipe[1] = -1;
  data.side_pipe[0]       = data.side_pipe[1] = -1;
  data.logfunc            = cfCUPSLogFunc;
  data.iscanceledfunc     = cfCUPSIsCanceledFunc;
  data.iscanceleddata     = &canceled;

  if (optstr)
    data.num_options = cupsParseOptions(optstr, NULL, 0, &data.options);

  if ((fontpath = getenv("CUPS_FONTPATH")) != NULL && !cupsGetOption("cups-fontpath", data.num_options, data.options))
    data.num_options = cupsAddOption("cups-fontpath", fontpath, data.num_options, &data.options);

  if (chain_spec && *chain_spec)
  {
    chain = parse_chain(chain_spec, &ctx);
    ret   = cfFilterChain(inputfd, outputfd, 0, &data, chain);

    while ((f = cupsArrayGetFirst(chain)) != NULL)
    {
      cupsArrayRemove(chain, f);
      free(f->parameters);
      free(f);
    }
    cupsArrayDelete(chain);
  }
  else
  {
    cf_filter_universal_parameter_t up;

    memset(&up, 0, sizeof(up));
    up.actual_output_type       = (char *)out_type;
    up.texttopdf_params         = ctx.texttopdf;
    up.bannertopdf_template_dir = ctx.banner_dir;
    ret = cfFilterUniversal(inputfd, outputfd, 0, &data, &up);
  }

  close(outputfd);
  cupsFreeOptions(data.num_options, data.options);
  ippDelete(data.printer_attrs);
  free(chain_spec);

  return (ret);
}
