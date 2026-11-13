import { MeetingSettings } from '@/features/settings/MeetingSettings';
import { PasswordCard } from '@/features/auth/PasswordCard';
import { ProfileCard } from '@/features/auth/ProfileCard';

/** Личный кабинет: профиль, пароль и параметры новых встреч. */
export function SettingsPage() {
  return (
    <section className="flex max-w-2xl flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">Настройки</h1>
        <p className="text-base text-muted-foreground">Ваш профиль и безопасность аккаунта.</p>
      </header>
      <MeetingSettings />
      <ProfileCard />
      <PasswordCard />
    </section>
  );
}
