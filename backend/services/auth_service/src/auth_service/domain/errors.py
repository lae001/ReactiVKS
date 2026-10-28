"""Ошибки, которые обнаруживают правила auth-service. Коды – из реестра docs/api/rest-api.md."""

from vks_common.errors import Conflict, Forbidden, NotFound, Unauthorized, ValidationFailed

__all__ = [
    "AccountGone",
    "EmailTaken",
    "InvalidCredentials",
    "InvalidDisplayName",
    "InvalidEmail",
    "LastAdmin",
    "RegistrationClosed",
    "SessionInvalid",
    "UserBlocked",
    "UserNotFound",
    "WeakPassword",
]


class InvalidEmail(ValidationFailed):
    """Строка не похожа на адрес электронной почты."""

    title = "Email is not valid"


class InvalidDisplayName(ValidationFailed):
    """Имя пустое или длиннее допустимого."""

    title = "Display name is not valid"


class WeakPassword(ValidationFailed):
    """Пароль не удовлетворяет политике. ``detail`` называет правило и никогда не цитирует пароль."""

    title = "Password is too weak"


class EmailTaken(Conflict):
    """Адрес уже занят другой учетной записью."""

    code = "email_taken"
    title = "Email is already registered"


class InvalidCredentials(Unauthorized):
    """Вход не удался, и ответ не говорит почему: неизвестный адрес и неверный пароль неотличимы."""

    code = "invalid_credentials"
    title = "Email or password is not correct"


class UserBlocked(Forbidden):
    """Пароль верный, но учетная запись заблокирована администратором."""

    code = "user_blocked"
    title = "User is blocked"


class SessionInvalid(Unauthorized):
    """Refresh-токен неизвестен, истек, отозван или уже обменян.

    Один ответ на все причины: назвать повторное использование значило бы сообщить укравшему токен, что кража
    замечена.
    """


class RegistrationClosed(NotFound):
    """Открытая регистрация выключена (``AUTH_REGISTRATION_ENABLED=false``): эндпоинта как будто нет."""


class AccountGone(Unauthorized):
    """Access-токен еще действует, а учетной записи уже нет: для сервиса такой вызывающий не аутентифицирован."""


class UserNotFound(NotFound):
    """Учетной записи нет (или она удалена)."""


class LastAdmin(Conflict):
    """Администратор не блокирует, не понижает и не удаляет себя, а в Системе остается хотя бы один активный
    администратор: иначе управлять пользователями станет некому."""

    code = "last_admin"
    title = "The last administrator cannot be removed"
