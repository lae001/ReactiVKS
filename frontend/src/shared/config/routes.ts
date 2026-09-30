/** Пути приложения (docs/frontend/README.md, раздел «Маршруты»). */
export const paths = {
  login: '/login',
  register: '/register',
  meetings: '/meetings',
  meetingNew: '/meetings/new',
  meeting: (id: string) => `/meetings/${id}`,
  room: (meetingId: string) => `/room/${meetingId}`,
  join: (inviteCode: string) => `/j/${inviteCode}`,
  settings: '/settings',
  admin: '/admin',
  devUi: '/dev/ui',
  devLivekit: '/dev/livekit',
} as const;
