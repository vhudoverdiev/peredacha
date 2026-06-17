from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import BooleanField, PasswordField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional
from app.models import TASK_STATUSES, PRIORITIES, USER_ROLE_CHOICES


class LoginForm(FlaskForm):
    username = StringField("Логин", validators=[DataRequired(), Length(max=80)])
    password = PasswordField("Пароль", validators=[DataRequired()])
    remember = BooleanField("Запомнить меня")
    submit = SubmitField("Войти")


class LoginCaptchaForm(FlaskForm):
    captcha_answer = StringField("Ответ", validators=[DataRequired(), Length(max=10)])
    submit = SubmitField("Продолжить")


class UploadExcelForm(FlaskForm):
    file = FileField("Excel-файл .xlsx", validators=[FileRequired(), FileAllowed(["xlsx"], "Только .xlsx")])
    submit = SubmitField("Загрузить и синхронизировать")


class ProjectForm(FlaskForm):
    name = StringField("Название объекта", validators=[DataRequired(), Length(max=180)])
    address = StringField("Адрес", validators=[Optional(), Length(max=255)])
    description = TextAreaField("Описание", validators=[Optional(), Length(max=2000)])
    google_sheet_id = StringField("Google Sheet ID", validators=[Optional(), Length(max=255)])
    has_apartments = BooleanField("Квартиры", default=True)
    has_commercial = BooleanField("Коммерции", default=True)
    has_storerooms = BooleanField("Кладовки", default=False)
    submit = SubmitField("Создать объект")


class TaskEditForm(FlaskForm):
    status = SelectField("Статус", choices=[(k, v["label"]) for k, v in TASK_STATUSES.items()])
    priority = SelectField("Приоритет", choices=[(p, p) for p in PRIORITIES])
    responsible_id = SelectField("Ответственный", choices=[], validators=[Optional()])
    planned_date = StringField("Плановая дата", validators=[Optional()])
    comment = TextAreaField("Примечание", validators=[Optional()])
    submit = SubmitField("Сохранить")


class CommentForm(FlaskForm):
    body = TextAreaField("Комментарий", validators=[DataRequired(), Length(max=4000)])
    submit = SubmitField("Добавить комментарий")


class UserForm(FlaskForm):
    username = StringField("Логин", validators=[DataRequired(), Length(max=80)])
    full_name = StringField("Имя", validators=[Optional(), Length(max=160)])
    password = PasswordField("Пароль", validators=[Optional(), Length(min=8)])
    role = SelectField("Роль", choices=USER_ROLE_CHOICES)
    submit = SubmitField("Сохранить")


class UserPasswordForm(FlaskForm):
    password = PasswordField("Новый пароль", validators=[DataRequired(), Length(min=8)])
    submit = SubmitField("Сменить пароль")


class MappingForm(FlaskForm):
    submit = SubmitField("Сохранить соответствия")
