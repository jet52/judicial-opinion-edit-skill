SKILL_NAME := jetredline
ZIP_NAME := $(SKILL_NAME)-skill.zip

.PHONY: package clean install test

package: clean
	zip -r $(ZIP_NAME) skill/ install.sh README.md \
		-x "skill/.venv/*" "skill/node_modules/*" "skill/package-lock.json" "skill/__pycache__/*"

clean:
	rm -f $(ZIP_NAME)

install:
	bash install.sh

test:
	@echo "Validating skill structure..."
	@test -f skill/SKILL.md || (echo "FAIL: skill/SKILL.md missing" && exit 1)
	@test -d skill/references || (echo "FAIL: skill/references/ missing" && exit 1)
	@test -f skill/package.json || (echo "FAIL: skill/package.json missing" && exit 1)
	@test -f install.sh || (echo "FAIL: install.sh missing" && exit 1)
	@test -f README.md || (echo "FAIL: README.md missing" && exit 1)
	@echo "All checks passed."
