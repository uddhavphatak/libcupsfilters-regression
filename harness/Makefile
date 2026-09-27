# make PREFIX=/opt/baseline SIDE=baseline  ->  harness/harness-baseline
PREFIX ?= /usr
SIDE   ?= local
CC     ?= cc

PKG_CONFIG_PATH := $(PREFIX)/lib/pkgconfig:$(PKG_CONFIG_PATH)
export PKG_CONFIG_PATH

CFLAGS  ?= -O2 -g -Wall
PKGFLAGS = -I$(PREFIX)/include $(shell pkg-config --cflags cups)
PKGLIBS  = -L$(PREFIX)/lib -lcupsfilters $(shell pkg-config --libs cups)

harness-$(SIDE): harness.c
	$(CC) $(CFLAGS) $(PKGFLAGS) -o $@ $< $(PKGLIBS) -Wl,-rpath,$(PREFIX)/lib

clean:
	rm -f harness-*

.PHONY: clean
