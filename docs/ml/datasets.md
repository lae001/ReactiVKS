# Реестр датасетов и лицензий (EMO-5)

Ответственный – Лесовой А. Е. Реестр закрывает риск 10 устава (лицензии датасетов и весов) и фиксирует, что
используется для обучения и теста модели распознавания эмоций ([ml-model.md](ml-model.md)).

## Сводка

| Датасет | Объем | Классы | Формат | Лицензия / условия | Доступ | Статус |
|---|---|---|---|---|---|---|
| **FER-2013** | 35 887 (Training 28 709, PublicTest 3 589, PrivateTest 3 589) | 7 базовых | 48×48, серое, выровненные кропы | Данные соревнования Kaggle «Challenges in Representation Learning» (ICML 2013); явной открытой лицензии нет, принято использование в исследовательских и учебных целях | Открыт: Kaggle (нужна учетная запись) или зеркала на Hugging Face | **Загружен** (зеркало `Aaryan333/fer2013_train_publicTest_privateTest`, ревизия `da8d164`, исходные сплиты) |
| **RAF-DB** (basic) | 15 339 (train 12 271, test 3 068) | 7 базовых | Цветные, выровненные 100×100 + исходные | Только некоммерческие исследования; запрещена передача третьим лицам; требуется подписанное соглашение | По запросу авторам (BUPT, проф. Weihong Deng), письмо с университетского адреса | Запрос подготовлен ([шаблон](#шаблон-запроса-raf-db)) |
| **AffectNet** | ≈ 440 тыс. размечено вручную (train ≈ 287 тыс., val 4 000) | 8 (7 базовых + contempt), valence/arousal | Цветные, разные размеры, рамки и 68 точек лица | Только некоммерческие исследования; соглашение подписывает научный руководитель (студенту – через руководителя) | Форма запроса на сайте лаборатории M. Mahoor (University of Denver) | Запрос подготовлен ([шаблон](#шаблон-запроса-affectnet)) |
| FER+ (метки) | Те же 35 887 изображений FER-2013 | 8 + unknown / not face | Файл меток CSV (10 разметчиков на изображение) | MIT (репозиторий microsoft/FERPlus); изображения – по условиям FER-2013 | Открыт | Кандидат: чистые метки для обучения, если RAF-DB / AffectNet не будут получены |
| Собственная выборка | 3–5 ч записей встреч команды | 7 базовых | Кадры ВКС | Только участники команды, с письменного согласия; не публикуется | Локально у команды | Сбор в спринте 5 |

Порядок классов во всех датасетах приводится к контракту `angry, disgust, fear, happy, sad, surprise, neutral`
(`emotion_service/labels.py`). Класс `contempt` AffectNet исключается. Соответствие меток RAF-DB
(1 Surprise, 2 Fear, 3 Disgust, 4 Happiness, 5 Sadness, 6 Anger, 7 Neutral) реализовано в
`fer_training/data.py` (`RAFDB_TO_LABEL`).

## Ссылки на первоисточники

| Датасет | Публикация |
|---|---|
| FER-2013 | Goodfellow I. et al. Challenges in Representation Learning: A report on three machine learning contests. ICONIP 2013 |
| RAF-DB | Li S., Deng W., Du J. Reliable Crowdsourcing and Deep Locality-Preserving Learning for Expression Recognition in the Wild. CVPR 2017 |
| AffectNet | Mollahosseini A., Hasani B., Mahoor M. AffectNet: A Database for Facial Expression, Valence, and Arousal Computing in the Wild. IEEE TAC, 2017 |
| FER+ | Barsoum E. et al. Training Deep Networks for Facial Expression Recognition with Crowd-Sourced Label Distribution. ICMI 2016 |

## Выбор для проекта

1. **FER-2013 – основа и тест целевой метрики** (accuracy ≥ 65 % на PublicTest + PrivateTest). Открыт сразу,
   классы совпадают с ТЗ, лица уже выровнены. Недостатки (из EDA, [ноутбук](../../ml/training/notebooks/01_fer2013_eda.ipynb)):
   низкое разрешение, шумная разметка, сильный дисбаланс (disgust ≈ 1,5 %).
2. **RAF-DB – дообучение** (EMO-61): качественная разметка (≈ 40 разметчиков на изображение), условия «в дикой
   природе», ближе к кадрам ВКС, чем FER-2013.
3. **AffectNet – по доступности**: самый большой, но получение занимает недели и требует подписи руководителя.
   Используется только 7 базовых классов, с балансировкой.
4. Если ни RAF-DB, ни AffectNet не получены к спринту 4, резерв – метки FER+ (MIT) поверх тех же изображений.

## Ограничения использования

- Все датасеты – только для некоммерческого учебного проекта, что соответствует характеру Системы. Коммерческое
  использование обученной модели не допускается; это указано в `model_card.json` (`license_note`).
- Изображения датасетов **не** коммитятся в репозиторий (каталог `ml/training/data/` в `.gitignore`), не
  передаются третьим лицам и хранятся только на машинах участников команды (риск 8 устава).
- Веса, обученные на RAF-DB / AffectNet, публикуются только внутри команды (GitHub Releases приватного
  репозитория).
- Предобученные веса ImageNet (timm: ResNet-18 `a1_in1k`, EfficientNet-B0 `ra_in1k`, MobileNetV3-Large
  `ra_in1k`) – лицензия Apache 2.0.
- Детекторы лиц: YuNet (OpenCV Zoo) – MIT; MediaPipe BlazeFace – Apache 2.0.

## Шаблон запроса RAF-DB

Отправляется с университетского адреса, к письму прикладывается подписанное соглашение с сайта датасета.

> Subject: RAF-DB access request – student project, <университет>
>
> Dear Prof. Deng,
>
> I am a student at <университет>, working under the supervision of <ФИО руководителя> on an educational
> project: a video-conferencing application that estimates participants' facial expressions (7 basic emotions)
> with their explicit consent. We would like to use the RAF-DB basic subset strictly for non-commercial research
> and education: training and evaluating the expression classifier. The data will be stored only on the project
> team's machines and will not be redistributed.
>
> Please find the signed agreement attached. Thank you for considering our request.
>
> Best regards, Artem Lesovoy, <университет>, <email>

## Шаблон запроса AffectNet

Заполняется форма на сайте датасета; соглашение подписывает научный руководитель как ответственное лицо.
В поле назначения: «Non-commercial educational project: facial expression recognition (7 basic classes) for
a video-conferencing prototype; data stored on project machines only, no redistribution».

## Журнал

| Дата | Событие |
|---|---|
| 14.10.2026 | Реестр составлен; FER-2013 загружен (sha256 parquet-файлов – в `ml/training/data/README.md`); подготовлены запросы RAF-DB и AffectNet |
