import {
  type InfiniteData,
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';

import {
  type CreateMeetingRequest,
  type Meeting,
  type MeetingStatus,
  meetingsApi,
  type Page,
  type Settings,
  type UpdateMeetingRequest,
} from '@/shared/api/meetings';

/** Встреч за один запрос списка; «Ещё» подгружает следующую страницу по курсору. */
export const PAGE_SIZE = 20;

export const meetingKeys = {
  all: ['meetings'] as const,
  lists: () => [...meetingKeys.all, 'list'] as const,
  list: (filters: MeetingsFilters) => [...meetingKeys.lists(), filters] as const,
  detail: (id: string) => [...meetingKeys.all, 'detail', id] as const,
  participants: (id: string) => [...meetingKeys.all, 'participants', id] as const,
  settings: ['settings'] as const,
};

export interface MeetingsFilters {
  status?: MeetingStatus[];
  q?: string;
}

export function useMeetingsList(filters: MeetingsFilters) {
  return useInfiniteQuery({
    queryKey: meetingKeys.list(filters),
    queryFn: ({ pageParam, signal }) =>
      meetingsApi.listMeetings({ ...filters, limit: PAGE_SIZE, cursor: pageParam }, signal),
    // при смене поиска или фильтра прежний список остается на экране, пока не придет новый
    placeholderData: keepPreviousData,
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: Page<Meeting>) => last.next_cursor ?? undefined,
  });
}

export function useMeeting(id: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: meetingKeys.detail(id),
    queryFn: ({ signal }) => meetingsApi.getMeeting(id, signal),
    enabled: options.enabled,
  });
}

export function useParticipants(id: string, enabled = true) {
  return useQuery({
    queryKey: meetingKeys.participants(id),
    enabled,
    queryFn: ({ signal }) => meetingsApi.listParticipants(id, signal),
  });
}

export function useSettings() {
  return useQuery<Settings>({
    queryKey: meetingKeys.settings,
    queryFn: ({ signal }) => meetingsApi.getSettings(signal),
  });
}

/** Обновляет карточку встречи в кэше и помечает списки устаревшими. */
function useMeetingCache() {
  const queryClient = useQueryClient();
  return (meeting: Meeting) => {
    queryClient.setQueryData(meetingKeys.detail(meeting.id), meeting);
    void queryClient.invalidateQueries({ queryKey: meetingKeys.lists() });
  };
}

export function useCreateMeeting() {
  const remember = useMeetingCache();
  return useMutation({
    mutationFn: ({ body, key }: { body: CreateMeetingRequest; key: string }) =>
      meetingsApi.createMeeting(body, key),
    onSuccess: remember,
  });
}

export function useUpdateMeeting(id: string) {
  const remember = useMeetingCache();
  return useMutation({
    mutationFn: (body: UpdateMeetingRequest) => meetingsApi.updateMeeting(id, body),
    onSuccess: remember,
  });
}

export function useEndMeeting(id: string) {
  const remember = useMeetingCache();
  return useMutation({ mutationFn: () => meetingsApi.endMeeting(id), onSuccess: remember });
}

export function useDeleteMeeting(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => meetingsApi.deleteMeeting(id),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: meetingKeys.detail(id) });
      void queryClient.invalidateQueries({ queryKey: meetingKeys.lists() });
    },
  });
}

/**
 * Начало встречи организатором: первый вход активирует ее (POST /meetings/{id}/join).
 * Согласие организатора по умолчанию не дано – анализ включается им явно в комнате.
 */
export function useStartMeeting(meeting: Pick<Meeting, 'id' | 'analysis_enabled'>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      meetingsApi.joinAsOrganizer(meeting.id, meeting.analysis_enabled ? 'denied' : undefined),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: meetingKeys.all });
    },
  });
}

/** «Начать сейчас»: создать встречу без времени и сразу войти в нее организатором. */
export function useStartInstantMeeting() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (key: string) => {
      const meeting = await meetingsApi.createMeeting({ title: 'Быстрая встреча' }, key);
      await meetingsApi.joinAsOrganizer(
        meeting.id,
        meeting.analysis_enabled ? 'denied' : undefined,
      );
      return meeting;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: meetingKeys.all });
    },
  });
}

export function flattenPages(data: InfiniteData<Page<Meeting>> | undefined): Meeting[] {
  return data?.pages.flatMap((p) => p.items) ?? [];
}
