# Данные (не коммитятся)

| Каталог | Содержимое | Как получить |
|---|---|---|
| `fer2013/raw/*.parquet` | FER-2013, исходные сплиты Training / PublicTest / PrivateTest | см. ниже |
| `fer2013/fer2013.npz` | Кеш в каноническом виде (48×48, uint8) | `fer-train prepare` |
| `ferplus/fer2013new.csv` | FER+ – метки 10 разметчиков для изображений FER-2013 (MIT) | `curl -L -o data/ferplus/fer2013new.csv https://raw.githubusercontent.com/microsoft/FERPlus/master/fer2013new.csv` |
| `rafdb/` | RAF-DB basic в исходной раскладке (`EmoLabel/`, `Image/aligned/`) | по запросу авторам ([docs/ml/datasets.md](../../../docs/ml/datasets.md)) |

FER-2013 – зеркало `Aaryan333/fer2013_train_publicTest_privateTest` на Hugging Face, ревизия
`da8d1643649c86bfc2cffba5b744b51fdf329212`:

```bash
R=da8d1643649c86bfc2cffba5b744b51fdf329212
B=https://huggingface.co/datasets/Aaryan333/fer2013_train_publicTest_privateTest/resolve/$R/data
mkdir -p data/fer2013/raw
curl -L -o data/fer2013/raw/train.parquet       $B/train-00000-of-00001-5eab84e1c6a2fc27.parquet
curl -L -o data/fer2013/raw/publicTest.parquet  $B/publicTest-00000-of-00001-f41bb7384b8aad6e.parquet
curl -L -o data/fer2013/raw/privateTest.parquet $B/privateTest-00000-of-00001-4b8a0715cf1b7560.parquet
```

| Файл | SHA-256 |
|---|---|
| `train.parquet` | `b1c4bee933d41947d7d67648a54f3877de9365703f40117e0d59495c8eb6647a` |
| `publicTest.parquet` | `e9efe94c45b5af29ec2825abb8f0bf3583450edb915b2c6ab6d5566afbffc5a1` |
| `privateTest.parquet` | `e0b74317d8d3defc79961a297a651e23ee8b0785669484a258e7a389be1fcea0` |

Число изображений по классам совпадает с оригинальным `fer2013.csv` (Training 28 709, PublicTest 3 589,
PrivateTest 3 589).
