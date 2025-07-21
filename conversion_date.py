# fonction permettant de convertir n'importe quel format de date vers le format de date "yyyy-mm-dd %" du GPKG
def convert_to_iso_date(value):
    # import des librairies concernées
    from PyQt5.QtCore import QDate, QDateTime
    from datetime import datetime, date
    import re

    # gestion des objets QDate et QDateTime de PyQt5
    if isinstance(value, QDate):
        return value.toString('yyyy-MM-dd')
    elif isinstance(value, QDateTime):
        return value.date().toString('yyyy-MM-dd')

    # gestion des objets datetime
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d')
    elif isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    elif isinstance(value, str):  # gestion des différents formats
        try:
            # gestion du format avec fuseau horaire : DD/MM/YYYY HH:MM:SS.mmm GMT+XX:XX
            if 'GMT' in value or 'UTC' in value:
                date_match = re.match(r'^(\d{1,2}[/-]\d{1,2}[/-]\d{4})', value)
                if date_match:
                    date_part = date_match.group(1)
                    return self.convert_to_iso_date(date_part)  # conversion récursive de la partie date
                # si pas de match avec le pattern ci-dessus, essayer d'extraire YYYY-MM-DD
                iso_match = re.search(r'(\d{4}-\d{1,2}-\d{1,2})', value)
                if iso_match:
                    return iso_match.group(1)

            # essayage format DD/MM/YYYY
            if '/' in value and not 'GMT' in value and not 'UTC' in value:
                # vérifier si c'est juste DD/MM/YYYY ou DD/MM/YYYY avec heure
                date_part = value.split(' ')[0] if ' ' in value else value
                if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', date_part):
                    dt = datetime.strptime(date_part, '%d/%m/%Y')
                    return dt.strftime('%Y-%m-%d')

            # essayage format DD-MM-YYYY
            elif '-' in value and len(value.split('-')) == 3:
                # extraction de la partie date si il y a une heure
                date_part = value.split(' ')[0] if ' ' in value else value
                if re.match(r'^\d{1,2}-\d{1,2}-\d{4}$', date_part):
                    dt = datetime.strptime(date_part, '%d-%m-%Y')
                    return dt.strftime('%Y-%m-%d')

            # essayage format YYYY-MM-DD
            elif '-' in value and value.count('-') == 2:
                # Pattern pour YYYY-MM-DD au début de la string
                iso_match = re.match(r'^(\d{4}-\d{1,2}-\d{1,2})', value)
                if iso_match:
                    return iso_match.group(1)
                # si déjà au bon format, extraire seulement la partie date
                if ' ' in value:
                    return value.split(' ')[0]
                else:
                    return value

            # gestion des formats avec heures mais sans fuseau
            elif ' ' in value and not 'GMT' in value and not 'UTC' in value:
                date_part = value.split(' ')[0]
                return self.convert_to_iso_date(date_part)

            # gestion des formats ISO avec T (ex: 2024-02-05T11:49:08)
            elif 'T' in value:
                date_part = value.split('T')[0]
                return date_part
            else:
                # essayer de parser comme datetime pour les autres formats
                # nettoyer d'abord la string des fuseaux horaires
                clean_value = re.sub(r'\s*(GMT|UTC)[+\-]\d{2}:\d{2}$', '', value)
                clean_value = re.sub(r'\.\d{3}$', '', clean_value)  # enlever les millisecondes
                try:
                    dt = datetime.fromisoformat(clean_value.replace('T', ' '))
                    return dt.strftime('%Y-%m-%d')
                except:
                    # dernier recours : essayer de trouver une date dans la string
                    date_patterns = [
                        r'(\d{4}-\d{1,2}-\d{1,2})',  # YYYY-MM-DD
                        r'(\d{1,2}/\d{1,2}/\d{4})',  # DD/MM/YYYY
                        r'(\d{1,2}-\d{1,2}-\d{4})'  # DD-MM-YYYY
                    ]
                    for pattern in date_patterns:
                        match = re.search(pattern, value)
                        if match:
                            found_date = match.group(1)
                            return self.convert_to_iso_date(found_date)
        except Exception as e:
            print(f"Erreur conversion date '{value}': {e}")
            return str(value)
    else:
        return str(value)