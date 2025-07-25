#!/bin/bash
set -e

# Параметры из аргументов
ORANGE_PI_USER="$1"
ORANGE_PI_IP="$2"
PROJECT_DIR="$3"
TARGET_BINARY="$4"
VERSION="$5"

LOCAL_BIN_DIR="./bin"

echo "Начинаем сборку $TARGET_BINARY версии $VERSION для Orange Pi 5 Max"

# 1. Копируем проект на Orange Pi
echo "Копируем файлы на Orange Pi..."
rsync -avz --delete \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='bin' \
    --exclude='dist' \
    --exclude='build' \
    --exclude='.venv' \
    --exclude='licenses' \
    --exclude='CHANGELOG.md' \
    --exclude='.env' \
    --exclude='devices.json' \
    --exclude='local_scan.json' \
    --exclude='Makefile' \
    --exclude='THIRD-PARTY-LICENSES' \
    --exclude='uv.lock' \
    --exclude='.gitignore' \
    ./ \
    $ORANGE_PI_USER@$ORANGE_PI_IP:$PROJECT_DIR

# 2. Запускаем сборку на Orange Pi
echo "Запускаем сборку на Orange Pi..."
ssh $ORANGE_PI_USER@$ORANGE_PI_IP "cd $PROJECT_DIR && build_scripts/build.sh '$VERSION' '$TARGET_BINARY'"

# 3. Копируем результат обратно
echo "Забираем собранный бинарник..."
mkdir -p "$LOCAL_BIN_DIR/$VERSION"
scp $ORANGE_PI_USER@$ORANGE_PI_IP:$PROJECT_DIR/dist/$TARGET_BINARY-$VERSION \
    "$LOCAL_BIN_DIR/$VERSION/"

# 4. Проверяем результат
if [ -f "$LOCAL_BIN_DIR/$VERSION/$TARGET_BINARY" ]; then
    echo -e "\nСборка успешно завершена!"
    echo "Бинарник: $LOCAL_BIN_DIR/$VERSION/$TARGET_BINARY"
    echo "Проверка: file $LOCAL_BIN_DIR/$VERSION/$TARGET_BINARY"
    file "$LOCAL_BIN_DIR/$VERSION/$TARGET_BINARY"
else
    echo "Ошибка: бинарник не найден"
    exit 1
fi