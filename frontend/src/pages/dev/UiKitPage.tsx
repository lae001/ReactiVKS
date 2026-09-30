import { EMOTION_LABELS, EMOTION_META } from '@/shared/config/emotions';
import { Badge } from '@/shared/ui/badge';
import { EmotionSpectrum, Wordmark } from '@/shared/ui/brand';
import { Button } from '@/shared/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card';
import { Input } from '@/shared/ui/input';
import { Label } from '@/shared/ui/label';

const BASE = [
  ['Бумага', '--background', 'фон приложения'],
  ['Чернила', '--foreground', 'основной текст'],
  ['Петроль', '--primary', 'действия, ссылки, фокус'],
  ['Приглушенный', '--muted-foreground', 'второстепенный текст'],
  ['Сигнал', '--signal', 'идет анализ, отметки моментов'],
  ['Ошибка', '--destructive', 'ошибки, завершение встречи'],
  ['Комната', '--room', 'фон видеовстречи'],
] as const;

function Swatch({ name, cssVar, note }: { name: string; cssVar: string; note: string }) {
  return (
    <div className="flex items-center gap-3">
      <span
        className="size-10 shrink-0 rounded-md border"
        style={{ background: `var(${cssVar})` }}
      />
      <div className="text-sm">
        <p className="font-medium">{name}</p>
        <p className="text-muted-foreground">
          <code>{cssVar}</code> — {note}
        </p>
      </div>
    </div>
  );
}

/** UI-кит (EMO-18): живая витрина токенов и компонентов. Доступна только в dev-сборке. */
export default function UiKitPage() {
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-10 px-6 py-10">
      <header className="flex flex-col gap-4">
        <Wordmark />
        <h1 className="text-3xl font-semibold tracking-tight">UI-кит</h1>
        <p className="max-w-prose text-muted-foreground">
          Токены из <code>src/app/styles.css</code> и базовые компоненты shadcn/ui. Обоснование —
          docs/frontend/ui-kit.md.
        </p>
      </header>

      <section className="grid gap-4 sm:grid-cols-2">
        <h2 className="text-lg font-semibold sm:col-span-2">Базовая палитра</h2>
        {BASE.map(([name, v, note]) => (
          <Swatch key={v} name={name} cssVar={v} note={note} />
        ))}
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold">
          Эмоции <Badge variant="outline">черновик, EMO-56</Badge>
        </h2>
        <EmotionSpectrum className="h-2 max-w-md" />
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-4">
          {EMOTION_LABELS.map((e) => (
            <Swatch key={e} name={EMOTION_META[e].title} cssVar={EMOTION_META[e].cssVar} note={e} />
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold">Типографика — Onest</h2>
        <p className="text-3xl font-semibold tracking-tight">Встреча с командой продукта</p>
        <p className="text-xl font-medium">Панель эмоций</p>
        <p className="max-w-prose text-base">
          Организатор видит распознанные эмоции участников, давших согласие. Результаты носят
          вероятностный характер.
        </p>
        <p className="text-sm text-muted-foreground">Радость 71 % · Нейтральное 18 % · 12:04:33</p>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold">Кнопки и метки</h2>
        <div className="flex flex-wrap gap-3">
          <Button>Создать встречу</Button>
          <Button variant="outline">Скопировать ссылку</Button>
          <Button variant="secondary">Отметить момент</Button>
          <Button variant="ghost">Отмена</Button>
          <Button variant="destructive">Завершить встречу</Button>
          <Button disabled>Недоступно</Button>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge>Идет</Badge>
          <Badge variant="secondary">Запланирована</Badge>
          <Badge variant="outline">Завершена</Badge>
          <Badge variant="signal">Идет анализ эмоций</Badge>
          <Badge variant="destructive">Анализ недоступен</Badge>
        </div>
      </section>

      <section className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Форма</CardTitle>
            <CardDescription>Поле, подпись и состояние ошибки</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="kit-title">Название встречи</Label>
              <Input id="kit-title" placeholder="Еженедельная планерка" />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="kit-err">Электронная почта</Label>
              <Input id="kit-err" aria-invalid defaultValue="anna@" />
              <p className="text-sm text-destructive">
                Укажите адрес полностью, например anna@mail.ru
              </p>
            </div>
          </CardContent>
        </Card>
        <div className="dark flex flex-col gap-3 rounded-xl bg-room p-6 text-room-foreground">
          <p className="text-sm font-medium">Тёмная тема комнаты</p>
          <div className="flex flex-wrap gap-2">
            <Button variant="room">Камера</Button>
            <Button>Пригласить</Button>
            <Button variant="destructive">Завершить</Button>
          </div>
          <Badge variant="signal">Идет анализ эмоций</Badge>
        </div>
      </section>
    </div>
  );
}
