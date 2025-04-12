from quart_wtf import QuartForm
from wtforms import SubmitField

class DevicesForm(QuartForm):
    submit = SubmitField('Save')
