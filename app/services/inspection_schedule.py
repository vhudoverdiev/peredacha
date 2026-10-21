"""Downloadable daily inspection agenda, rendered without a browser or cloud service."""
from io import BytesIO
from pathlib import Path
from datetime import date
import re
from PIL import Image, ImageDraw, ImageFont


def inspection_contact_lines(value):
    text = str(value or '').strip()
    if not text:
        return ''
    parts = [part.strip() for part in re.split(r'\n+|\s*;\s*', text) if part.strip()]
    if len(parts) > 1:
        return '\n'.join(parts)
    words = parts[0].split()
    if len(words) >= 6 and len(words) % 3 == 0:
        return '\n'.join(' '.join(words[index:index + 3]) for index in range(0, len(words), 3))
    return parts[0]


def inspection_phone_lines(value):
    text = str(value or '').strip()
    if not text:
        return ''
    phones = re.findall(r'(?<!\d)(?:\+?7|8)[\s(]*\d{3}\)?[\s-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)', text)
    if len(phones) > 1:
        return '\n'.join(phone.strip() for phone in phones)
    return '\n'.join(part.strip() for part in re.split(r'\n+|\s*[;,]\s*', text) if part.strip())


def has_prior_inspection(apartment, day):
    """A previous dated inspection, not the current scheduled appointment."""
    values = (apartment.inspection_date, apartment.inspection_date_backup,
              apartment.first_inspection_date, apartment.reinspection_date)
    if any(value is not None and value < day for value in values):
        return True
    for raw in re.findall(r'Дополнительный осмотр:\s*(\d{2}\.\d{2}\.\d{4})', apartment.inspection_note or ''):
        try:
            if date.fromisoformat(f'{raw[6:10]}-{raw[3:5]}-{raw[:2]}') < day:
                return True
        except ValueError:
            pass
    return any(booking.status == 'completed' and booking.slot.day < day
               for booking in apartment.inspection_bookings)


def _font(size, bold=False):
    names = (['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
              '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf',
              '/System/Library/Fonts/Supplemental/Arial Bold.ttf', 'C:/Windows/Fonts/arialbd.ttf'] if bold else
             ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
              '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
              '/System/Library/Fonts/Supplemental/Arial.ttf', 'C:/Windows/Fonts/arial.ttf'])
    for name in names:
        if Path(name).is_file():
            return ImageFont.truetype(name,size)
    # RHEL and Debian package the same fonts under different subdirectories.
    for root in (Path('/usr/share/fonts'), Path('/usr/local/share/fonts')):
        if root.is_dir():
            for filename in (['DejaVuSans-Bold.ttf', 'LiberationSans-Bold.ttf'] if bold else ['DejaVuSans.ttf', 'LiberationSans-Regular.ttf']):
                match = next(root.rglob(filename), None)
                if match:
                    return ImageFont.truetype(str(match), size)
    raise RuntimeError('Для изображения расписания нужен системный шрифт Arial или DejaVu Sans.')


def render_schedule_png(project, day, bookings, slots=None):
    """Daily sheet in the supplied design, including available empty rows."""
    regular = _font(23)
    bold = _font(24, True)
    title_font = _font(54, True)
    date_font = _font(44, True)
    probe = ImageDraw.Draw(Image.new('RGB', (1, 1)))

    def wrapped(value, width):
        lines = []
        for paragraph in str(value or '').splitlines():
            line = ''
            for word in paragraph.split():
                candidate = f'{line} {word}' if line else word
                if line and probe.textlength(candidate, font=regular) > width:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
        return lines or ['']

    booked = {booking.slot_id: booking for booking in bookings}
    if slots is None:
        slots = [booking.slot for booking in bookings]
    slots = sorted(slots, key=lambda slot: slot.start_time)
    widths = [72, 160, 175, 160, 710, 459]
    rows = []
    for index, slot in enumerate(slots, 1):
        booking = booked.get(slot.id)
        apartment = booking.apartment if booking else None
        values = [str(index), (booking.appointment_time or slot.start_time).strftime('%H:%M') if booking else slot.start_time.strftime('%H:%M'),
                  apartment.label() if apartment else '',
                  apartment.finishing_type if apartment else '',
                  (inspection_contact_lines(booking.contact or apartment.owner_name) + (' (ПО)' if has_prior_inspection(apartment, day) else '')) if booking else '',
                  (booking.contact_phone or apartment.phone) if booking else '']
        lines = [wrapped(value, width - 32) for value, width in zip(values, widths)]
        rows.append((lines, max(70, 28 + max(map(len, lines)) * 32), bool(booking)))
    width = 1888
    height = max(520, 468 + sum(row[1] for row in rows))
    image = Image.new('RGB', (width, height), '#f7f8f3')
    draw = ImageDraw.Draw(image)
    left, right, top = 49, width - 49, 56
    bottom = height - 56
    draw.rounded_rectangle((left, top, right, bottom), radius=30, fill='white')
    draw.rounded_rectangle((left, top, right, 265), radius=30, fill='#1d372c')
    draw.rectangle((left, 160, right, 265), fill='#1d372c')
    # Use the same mark as the sidebar, with a quiet frame that sits naturally
    # against the dark CRM header.
    logo_path = Path(__file__).resolve().parents[1] / 'static' / 'brand-logo.png'
    with Image.open(logo_path) as source:
        logo = source.convert('RGBA').resize((112, 112), Image.Resampling.LANCZOS)
    logo_mask = Image.new('L', (112, 112), 0)
    ImageDraw.Draw(logo_mask).rounded_rectangle((0, 0, 111, 111), radius=25, fill=255)
    image.paste(logo, (88, 105), logo_mask)
    draw.text((228, 112), 'Записи на осмотры', font=_font(46, True), fill='white')
    project_name = str(getattr(project, 'name', '') or '').strip()
    if project_name:
        subtitle = project_name
        subtitle_font = _font(23)
        while subtitle and draw.textlength(subtitle, font=subtitle_font) > 1030:
            subtitle = subtitle[:-2].rstrip() + '…'
        draw.text((230, 183), subtitle, font=subtitle_font, fill='#c9d8cb')
    months = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря']
    weekdays = ['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье']
    draw.rounded_rectangle((1350, 86, 1777, 235), radius=23, fill='#28493a', outline='#416750', width=2)
    draw.text((1380, 108), f'{day.day} {months[day.month-1]}', font=_font(40, True), fill='white')
    draw.text((1383, 177), f'{day.year}  ·  {weekdays[day.weekday()]}', font=regular, fill='#c9d8cb')
    y = 281
    x = 76
    for label, col_width in zip(['№','Время','Квартира','Отделка','ФИО','Телефон'], widths):
        draw.rectangle((x, y, x+col_width, y+63), fill='#f0f3eb')
        draw.text((x+16, y+20), label, font=_font(21, True), fill='#3a4b3c')
        x += col_width
    y += 63
    for lines, row_height, occupied in rows:
        if occupied:
            draw.rectangle((76, y, 1812, y+row_height), fill='#f0f7e5')
            draw.rectangle((76, y, 82, y+row_height), fill='#8cdd0a')
        x = 76
        for column, (column_lines, col_width) in enumerate(zip(lines, widths)):
            font = bold if column == 1 else regular
            for line_index, line in enumerate(column_lines):
                draw.text((x+16, y+16+line_index*32), line,
                          font=font, fill='#959e97' if column == 0 else '#17212b')
            x += col_width
        draw.line((76, y+row_height-1, 1812, y+row_height-1), fill='#dfe3de', width=1)
        y += row_height
    if not rows:
        draw.text((92, y+28), 'На этот день время для записи не задано.', font=regular, fill='#17212b')
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()
