import { CameraOff } from 'lucide-react';
import { useParams } from 'react-router';

import { checkWebRtcSupport, describeWebRtcProblem } from '@/shared/lib/webrtc-support';
import { Wordmark } from '@/shared/ui/brand';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { Label } from '@/shared/ui/label';

/**
 * UC-3. Лобби гостя: проверка устройств, имя, решение о согласии на анализ.
 * Запросы GET/POST /api/v1/join/{invite_code} и предпросмотр камеры – спринт 4.
 */
export function JoinPage() {
  const { inviteCode = '' } = useParams();
  const problem = describeWebRtcProblem(checkWebRtcSupport());

  return (
    <div className="flex min-h-dvh flex-col px-4 py-8 md:px-10">
      <Wordmark />
      <main className="mx-auto grid w-full max-w-5xl flex-1 content-center gap-10 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="flex aspect-video items-center justify-center rounded-xl bg-room text-room-muted">
          <div className="flex flex-col items-center gap-2 text-sm">
            <CameraOff className="size-6" aria-hidden />
            Предпросмотр камеры
          </div>
        </div>

        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-1">
            <p className="text-sm text-muted-foreground">Приглашение {inviteCode}</p>
            <h1 className="text-xl font-semibold tracking-tight">Встреча еще не загружена</h1>
          </div>

          {problem && (
            <p
              role="alert"
              className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm"
            >
              {problem}
            </p>
          )}

          <div className="flex flex-col gap-2">
            <Label htmlFor="display-name">Как вас представить</Label>
            <Input id="display-name" autoComplete="name" placeholder="Имя" />
          </div>

          <fieldset className="flex flex-col gap-2 rounded-lg border p-4">
            <legend className="px-1 text-sm font-medium">Анализ эмоций</legend>
            <p className="text-sm text-muted-foreground">
              Организатор увидит, какие эмоции распознаны по вашему лицу. Видео не записывается.
              Решение можно изменить во время встречи.
            </p>
            <label className="flex items-center gap-2 text-sm">
              <input type="radio" name="consent" value="granted" className="accent-primary" />
              Разрешаю анализ
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="radio" name="consent" value="denied" className="accent-primary" />
              Участвую без анализа
            </label>
          </fieldset>

          <Button size="lg" disabled title="Подключается в спринте 4 (UC-3)">
            Войти во встречу
          </Button>
        </div>
      </main>
    </div>
  );
}
