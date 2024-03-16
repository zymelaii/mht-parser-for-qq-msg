all: build
.PHONY: all

build: mht-extract
.PHONY: build

clean:
	@rm -f mht-extract
.PHONY: clean

mht-extract: mht-extract.cpp base64.h
	@g++ -o $@ $< -O3 -std=c++20
.PHONY: build
