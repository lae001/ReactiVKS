#!/usr/bin/env sh
# Детекторы лиц и сетка лица для emotion_service и сравнения детекторов (EMO-44). Запуск из ml/models.
set -eu
mkdir -p yunet mediapipe
curl -fsSL -o yunet/face_detection_yunet_2023mar.onnx \
  https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
curl -fsSL -o mediapipe/blaze_face_short_range.tflite \
  https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite
curl -fsSL -o mediapipe/face_landmarker.task   https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task
sha256sum -c <<SUMS
8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4  yunet/face_detection_yunet_2023mar.onnx
b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f  mediapipe/blaze_face_short_range.tflite
64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff  mediapipe/face_landmarker.task
SUMS
