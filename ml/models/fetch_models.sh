#!/usr/bin/env sh
# Веса для emotion_service: детекторы и сетка лица (сторонние) и модели эмоций / внешних признаков из GitHub Releases
# репозитория (EMO-114). Запуск из ml/models; версия выпуска – ML_RELEASE (по умолчанию ml-v1.2.0).
set -eu
mkdir -p yunet mediapipe emotion emotion-robust attributes
curl -fsSL -o yunet/face_detection_yunet_2023mar.onnx \
  https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
curl -fsSL -o mediapipe/blaze_face_short_range.tflite \
  https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite
curl -fsSL -o mediapipe/face_landmarker.task   https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task

ML_RELEASE="${ML_RELEASE:-ml-v1.2.0}"
BASE="https://github.com/lae001/ReactiVKS/releases/download/$ML_RELEASE"
curl -fsSL -o emotion/emotion-efficientnetb0-v1.2.0.onnx "$BASE/emotion-efficientnetb0-v1.2.0.onnx"
curl -fsSL -o emotion-robust/emotion-efficientnetb0-v1.3.0.onnx "$BASE/emotion-efficientnetb0-v1.3.0.onnx"
curl -fsSL -o attributes/attributes-mobilenetv3-v1.0.0.onnx "$BASE/attributes-mobilenetv3-v1.0.0.onnx"

sha256sum -c <<SUMS
8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4  yunet/face_detection_yunet_2023mar.onnx
b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f  mediapipe/blaze_face_short_range.tflite
64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff  mediapipe/face_landmarker.task
f83deb9dff374986ba03718b5c07d3ff50c5744fbefec1a19fb54cfee24da215  emotion/emotion-efficientnetb0-v1.2.0.onnx
ef4567824e13d003b54f8bd99d90871395babc3f4b39d0913b2e305386b1205e  emotion-robust/emotion-efficientnetb0-v1.3.0.onnx
da1d4a10a7fc9cd7ff638a250224f00f78474c672e563b20932d442769fe86e2  attributes/attributes-mobilenetv3-v1.0.0.onnx
SUMS
