#!/bin/bash
set -e

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <version> <target_binary>"
    exit 1
fi

VERSION="$1"
TARGET_BINARY="$2"
BUILD_DIR="./build"
DIST_DIR="./dist"
VENV_DIR="/tmp/build-venv-$VERSION"

echo "Начинаем сборку $TARGET_BINARY версии $VERSION на $(hostname)"
echo "Архитектура: $(uname -m)"

# 1. Обновление системы (опционально)
# echo "Обновление пакетов..."
# sudo apt-get update > /dev/null

# 2. Создаем временное виртуальное окружение
echo "Создаем виртуальное окружение..."
export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH
python3.13 -m venv $VENV_DIR
source $VENV_DIR/bin/activate

# 3. Устанавливаем базовые зависимости
echo "Устанавливаем зависимости..."
pip install --upgrade pip setuptools wheel > /dev/null
pip install pyinstaller > /dev/null

# 4. Устанавливаем зависимости проекта
if [ -f "pyproject.toml" ]; then
    echo "Установка зависимостей проекта..."
    pip install -e . > /dev/null
else
    echo "Предупреждение: pyproject.toml не найден, зависимости не установлены"
fi

# 5. Выполняем сборку с PyInstaller
echo "Запускаем PyInstaller..."
pyinstaller \
    --onefile \
    --name "$TARGET_BINARY-$VERSION" \
    --distpath $DIST_DIR \
    --workpath "$BUILD_DIR/$VERSION" \
    --specpath "$BUILD_DIR/$VERSION" \
    --clean \
    $TARGET_BINARY.py

# 6. Проверяем результат
if [ -f "$DIST_DIR/$TARGET_BINARY-$VERSION" ]; then
    echo "Бинарник успешно создан: $DIST_DIR/$TARGET_BINARY-$VERSION"
    echo "Информация о бинарнике:"
    file "$DIST_DIR/$TARGET_BINARY-$VERSION"
    ldd "$DIST_DIR/$TARGET_BINARY-$VERSION" || true
else
    echo "Ошибка: PyInstaller не создал бинарник"
    exit 1
fi

# 7. Очистка
echo "Очищаем временные файлы..."
deactivate
rm -rf $VENV_DIR
rm -rf "$BUILD_DIR/$VERSION"

echo "Сборка завершена успешно!"