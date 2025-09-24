play:
	docker build -t harness-cd-to-iacm .
	docker run -it --rm -v "$(pwd)/config.toml:/harness/config.toml" -e CONFIG_FILE=/harness/config.toml harness-cd-to-iacm