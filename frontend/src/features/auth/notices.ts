import { create } from 'zustand';

/**
 * Одноразовое сообщение для страницы входа. Передается через стор, а не через state перехода:
 * после очистки сессии на /login ведет охранник RequireAuth со своим state, и чужой state терялся бы.
 */
export type LoginNotice = 'password_changed';

interface NoticeState {
  notice: LoginNotice | null;
}

export const useLoginNotice = create<NoticeState>(() => ({ notice: null }));

export function setLoginNotice(notice: LoginNotice | null) {
  useLoginNotice.setState({ notice });
}
