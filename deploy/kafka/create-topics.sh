#!/bin/sh
# Создает топики из topics.yaml и приводит retention.ms к описанному. Идемпотентен: повторный запуск
# не меняет существующие топики, кроме retention. Число партиций только растет (уменьшить нельзя).
# Учетные записи SCRAM и ACL для production добавляются в EMO-71.
set -eu

BOOTSTRAP="${KAFKA_BOOTSTRAP_SERVERS:-kafka:19092}"
TOPICS_FILE="${TOPICS_FILE:-/scripts/topics.yaml}"
BIN=/opt/kafka/bin

awk '
  /^[[:space:]]*#/ { next }
  /- name:/        { name = $3 }
  /partitions:/    { partitions = $2 }
  /retention_ms:/  { print name, partitions, $2 }
' "$TOPICS_FILE" | while read -r name partitions retention; do
  "$BIN/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" --create --if-not-exists \
    --topic "$name" --partitions "$partitions" --replication-factor 1 \
    --config "retention.ms=$retention" --config min.insync.replicas=1
  "$BIN/kafka-configs.sh" --bootstrap-server "$BOOTSTRAP" --alter \
    --entity-type topics --entity-name "$name" --add-config "retention.ms=$retention" >/dev/null
  echo "topic $name: partitions=$partitions retention.ms=$retention"
done
