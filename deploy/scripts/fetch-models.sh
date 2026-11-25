#!/usr/bin/env sh
# Веса моделей ML-сервиса в ml/models (монтируется в контейнер как /models): см. ml/models/fetch_models.sh.
# Версия выпуска – ML_RELEASE (по умолчанию ml-v1.2.0).
set -eu
cd "$(dirname "$0")/../../ml/models"
exec sh ./fetch_models.sh
