import { useParams } from 'react-router-dom'
import { PagePlaceholder } from './PagePlaceholder'

export function LobbyPage() {
  const { inviteCode } = useParams()
  return (
    <PagePlaceholder
      title="Лобби"
      description={`Проверка устройств, имя, согласие на анализ. Код приглашения: ${inviteCode}`}
      access="все"
    />
  )
}
