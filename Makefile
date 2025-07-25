# Makefile для управления сборкой проекта
include build_config.cfg

# Получаем версию из pyproject.toml
VERSION := $(shell grep -Po '(?<=^version = ")[^"]*' pyproject.toml)

.PHONY: build clean deploy

build:
	@echo "Запуск сборки версии $(VERSION)"
	@./build_scripts/deploy_build.sh \
		"$(ORANGE_PI_USER)" \
		"$(ORANGE_PI_IP)" \
		"$(PROJECT_DIR)" \
		"$(TARGET_BINARY)" \
		"$(VERSION)"
	@echo "Сборка завершена: bin/$(VERSION)/$(TARGET_BINARY)"

clean:
	@echo "Очистка артефактов сборки..."
	@rm -rf bin/* build_scripts/__pycache__ 
	@ssh $(ORANGE_PI_USER)@$(ORANGE_PI_IP) "rm -rf $(PROJECT_DIR)/build $(PROJECT_DIR)/dist"
	@echo "Очистка завершена"

show-config:
	@echo "Текущая конфигурация:"
	@echo "  Пользователь: $(ORANGE_PI_USER)"
	@echo "  IP: $(ORANGE_PI_IP)"
	@echo "  Директория: $(PROJECT_DIR)"
	@echo "  Бинарник: $(TARGET_BINARY)"
	@echo "  Версия: $(VERSION)"