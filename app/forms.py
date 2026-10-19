from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import BooleanField, PasswordField, RadioField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, ValidationError
from app.models import TASK_STATUSES, PRIORITIES, USER_ROLE_CHOICES


class LoginForm(FlaskForm):
    username = StringField("Логин", validators=[DataRequired(), Length(max=80)])
    password = PasswordField("Пароль", validators=[DataRequired()])
    remember = BooleanField("Запомнить меня")
    submit = SubmitField("Войти")


class LoginCaptchaForm(FlaskForm):
    captcha_answer = StringField("Ответ", validators=[DataRequired(), Length(max=10)])
    submit = SubmitField("Продолжить")


class LoginTwoFactorForm(FlaskForm):
    two_factor_code = StringField("Код", validators=[DataRequired(), Length(min=6, max=8)])
    submit = SubmitField("Войти")


class UploadExcelForm(FlaskForm):
    file = FileField("Excel-файл .xlsx", validators=[FileRequired(), FileAllowed(["xlsx"], "Только .xlsx")])
    submit = SubmitField("Загрузить и синхронизировать")


class ProjectForm(FlaskForm):
    signature = FileField("Подпись", validators=[FileAllowed(["png", "jpg", "jpeg"], "Загрузите PNG или JPEG.")])
    remove_signature = BooleanField("Удалить загруженную подпись")

    def validate_signature(self, field):
        if not field.data:
            return
        from app.services.project_signature import normalize_signature
        try:
            self.signature_image_data = normalize_signature(field.data)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    name = StringField("Название объекта", validators=[DataRequired(), Length(max=180)])
    address = StringField("Адрес", validators=[Optional(), Length(max=255)])
    technical_customer = StringField("Тех.заказчик", validators=[Optional(), Length(max=255)])
    developer_name = StringField("СЗ", validators=[Optional(), Length(max=255)])
    inn_kpp = StringField("ИНН/КПП", validators=[Optional(), Length(max=80)])
    ogrn = StringField("ОГРН", validators=[Optional(), Length(max=80)])
    legal_address = StringField("Юридический адрес", validators=[Optional(), Length(max=255)])
    developer_director = StringField("Директор СЗ", validators=[Optional(), Length(max=255)])
    developer_representative = StringField("Представитель Застройщика", validators=[Optional(), Length(max=255)])
    developer_representative_phone = StringField("Номер телефона", validators=[Optional(), Length(max=80)])
    description = TextAreaField("Описание", validators=[Optional(), Length(max=2000)])
    has_apartments = BooleanField("Квартиры", default=True)
    has_commercial = BooleanField("Коммерции", default=True)
    has_storerooms = BooleanField("Кладовки", default=False)
    has_parking = BooleanField("Парковки", default=False)
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
    full_name = StringField("ФИО", validators=[Optional(), Length(max=160)])
    email = StringField("Email", validators=[Optional(), Length(max=180)])
    phone = StringField("Номер телефона", validators=[Optional(), Length(max=80)])
    password = PasswordField("Пароль", validators=[DataRequired(), Length(min=8)])
    role = RadioField("Роль", choices=USER_ROLE_CHOICES, default=USER_ROLE_CHOICES[0][0])
    submit = SubmitField("Сохранить")


class UserPasswordForm(FlaskForm):
    password = PasswordField("Новый пароль", validators=[DataRequired(), Length(min=8)])
    submit = SubmitField("Сменить пароль")


class MappingForm(FlaskForm):
    submit = SubmitField("Сохранить соответствия")
