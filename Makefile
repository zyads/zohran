.PHONY: build serve
build: ; ./deploy/assemble.sh
serve: build ; cd dist && python3 -m http.server 8090
