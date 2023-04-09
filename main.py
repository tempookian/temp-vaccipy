#!/usr/bin/env python3

import argparse
import copy
import json
import os

from tools.exceptions import ValidationError, PushoverNotificationError, TelegramNotificationError
from tools.its import ImpfterminService
from tools.kontaktdaten import decode_wochentag, encode_wochentag, get_kontaktdaten, \
    validate_kontaktdaten, validate_datum
from tools.utils import create_missing_dirs, get_current_version, \
    get_latest_version, pushover_validation, remove_prefix, \
    telegram_validation, unique, update_available
from tools.chromium_downloader import check_chromium, download_chromium, check_webdriver, download_webdriver, current_platform

PATH = os.path.dirname(os.path.realpath(__file__))


def update_kontaktdaten_interactive(
        known_kontaktdaten,
        command,
        configure_notifications,
        filepath=None):
    """
    Interaktive Eingabe und anschließendes Abspeichern der Kontaktdaten.

    :param known_kontaktdaten: Bereits bekannte Kontaktdaten, die nicht mehr
        abgefragt werden sollen.
    :param command: Entweder "code" oder "search". Bestimmt, welche
        Kontaktdaten überhaupt benötigt werden.
    :param configure_notifications: Boolean - die Option zum einrichten von Pushover
        und Telegram wird nur bei true angezeigt
    :param filepath: Pfad zur JSON-Datei zum Abspeichern der Kontaktdaten.
        Default: data/kontaktdaten.json im aktuellen Ordner
    :return: Dictionary mit Kontaktdaten
    """

    assert (command in ["code", "search"])

    # Werfe Fehler, falls die übergebenen Kontaktdaten bereits ungültig sind.
    validate_kontaktdaten(known_kontaktdaten)

    kontaktdaten = copy.deepcopy(known_kontaktdaten)

    with open(filepath, 'w', encoding='utf-8') as file:
        if "plz_impfzentren" not in kontaktdaten:
            print(
                "Mit einem Code kann in mehreren Impfzentren gleichzeitig nach einem Termin gesucht werden.\n"
                "Eine Übersicht über die Gruppierung der Impfzentren findest du hier:\n"
                "https://github.com/iamnotturner/vaccipy/wiki/Ein-Code-fuer-mehrere-Impfzentren\n\n"
                "Trage nun die PLZ deines Impfzentrums ein. Für mehrere Impfzentren die PLZ's kommagetrennt nacheinander.\n"
                "Beispiel: 68163, 69124, 69469\n")
            input_kontaktdaten_key(kontaktdaten,
                                   ["plz_impfzentren"],
                                   "> PLZ's der Impfzentren: ",
                                   lambda x: unique([plz.strip() for plz in x.split(",")]))
            print()

        if "codes" not in kontaktdaten and command == "search":
            print(
                "Bitte gebe jetzt die Vermittlungscodes passend zu den ausgewählten Impfzentren ein.\n"
                "Beachte dabei, dass nur ein Vermittlungscode je Gruppierung benötigt wird.\n"
                "Weitere Infos: https://github.com/iamnotturner/vaccipy/wiki/Ein-Code-fuer-mehrere-Impfzentren\n\n"
                "Mehrere Vermittlungscodes müssen durch Kommas getrennt werden.\n"
                "Beispiel: ABCD-1234-EFGH, ABCD-4321-EFGH, 1234-56AB-CDEF\n")
            input_kontaktdaten_key(
                kontaktdaten, ["codes"], "> Vermittlungscodes: ",
                lambda x: unique([code.strip() for code in x.split(",")]))
            print()

        if "kontakt" not in kontaktdaten:
            kontaktdaten["kontakt"] = {}

        if "anrede" not in kontaktdaten["kontakt"] and command == "search":
            input_kontaktdaten_key(
                kontaktdaten, ["kontakt", "anrede"], "> Anrede (Frau/Herr/Kind/Divers): ")

        if "vorname" not in kontaktdaten["kontakt"] and command == "search":
            input_kontaktdaten_key(
                kontaktdaten, ["kontakt", "vorname"], "> Vorname: ")

        if "nachname" not in kontaktdaten["kontakt"] and command == "search":
            input_kontaktdaten_key(
                kontaktdaten, ["kontakt", "nachname"], "> Nachname: ")

        if "strasse" not in kontaktdaten["kontakt"] and command == "search":
            input_kontaktdaten_key(
                kontaktdaten, ["kontakt", "strasse"], "> Strasse (ohne Hausnummer): ")

        if "hausnummer" not in kontaktdaten["kontakt"] and command == "search":
            input_kontaktdaten_key(
                kontaktdaten, ["kontakt", "hausnummer"], "> Hausnummer: ")

        if "plz" not in kontaktdaten["kontakt"] and command == "search":
            input_kontaktdaten_key(
                kontaktdaten, ["kontakt", "plz"], "> PLZ des Wohnorts: ")

        if "ort" not in kontaktdaten["kontakt"] and command == "search":
            input_kontaktdaten_key(
                kontaktdaten, ["kontakt", "ort"], "> Wohnort: ")

        if "phone" not in kontaktdaten["kontakt"]:
            input_kontaktdaten_key(
                kontaktdaten,
                ["kontakt", "phone"],
                "> Telefonnummer: +49",
                lambda x: x if x.startswith("+49") else f"+49{remove_prefix(x, '0')}")

        if "notificationChannel" not in kontaktdaten["kontakt"]:
            kontaktdaten["kontakt"]["notificationChannel"] = "email"

        if "notificationReceiver" not in kontaktdaten["kontakt"]:
            input_kontaktdaten_key(
                kontaktdaten, ["kontakt", "notificationReceiver"], "> Mail: ")

        if configure_notifications:
            if "notifications" not in kontaktdaten:
                kontaktdaten["notifications"] = {}
            if "pushover" not in kontaktdaten["notifications"]:
                while True:
                    kontaktdaten["notifications"]["pushover"] = {}
                    if input("> Benachtigung mit Pushover einrichten? (y/n): ").lower() != "n":
                        print()
                        input_kontaktdaten_key(
                            kontaktdaten, ["notifications", "pushover", "app_token"],
                            "> Geben Sie den Pushover APP Token ein: ")
                        input_kontaktdaten_key(
                            kontaktdaten, ["notifications", "pushover", "user_key"],
                            "> Geben Sie den Pushover User Key ein: ")
                        try:
                            validation_code = str(pushover_validation(kontaktdaten["notifications"]["pushover"]))
                        except PushoverNotificationError as exc:
                            print(f"Fehler: {exc}\nBitte versuchen Sie es erneut.")
                            continue
                        validation_input = input("Geben Sie den Validierungscode ein:").strip()
                        if validation_input == validation_code:
                            break
                        del kontaktdaten["notifications"]["pushover"]
                        print("Validierung fehlgeschlagen.")
                        print()
                    else:
                        print()
                        break

            if "telegram" not in kontaktdaten["notifications"]:
                while True:
                    kontaktdaten["notifications"]["telegram"] = {}
                    if input("> Benachtigung mit Telegram einrichten? (y/n): ").lower() != "n":
                        print()
                        input_kontaktdaten_key(
                            kontaktdaten, ["notifications", "telegram", "api_token"],
                            "> Geben Sie den Telegram API Token ein: ")
                        input_kontaktdaten_key(
                            kontaktdaten, ["notifications", "telegram", "chat_id"],
                            "> Geben Sie die Telegram Chat ID ein: ")
                        try:
                            validation_code = str(telegram_validation(kontaktdaten["notifications"]["telegram"]))
                        except TelegramNotificationError as exc:
                            print(f"Fehler: {exc}\nBitte versuchen Sie es erneut.")
                            continue
                        validation_input = input("Geben Sie den Validierungscode ein:").strip()
                        if validation_input == validation_code:
                            break
                        del kontaktdaten["notifications"]["telegram"]
                        print("Validierung fehlgeschlagen.")
                        print()
                    else:
                        print()
                        break

        if "zeitrahmen" not in kontaktdaten and command == "search":
            kontaktdaten["zeitrahmen"] = {}
            if input("> Zeitrahmen festlegen? (y/n): ").lower() != "n":
                print()
                input_kontaktdaten_key(
                    kontaktdaten, ["zeitrahmen", "einhalten_bei"],
                    "> Für welchen Impftermin soll der Zeitrahmen gelten? (1/2/beide): ")
                input_kontaktdaten_key(
                    kontaktdaten, ["zeitrahmen", "von_datum"],
                    "> Von Datum (Leer lassen zum Überspringen): ",
                    lambda x: x if x else None)  # Leeren String zu None umwandeln
                input_kontaktdaten_key(
                    kontaktdaten, ["zeitrahmen", "bis_datum"],
                    "> Bis Datum (Leer lassen zum Überspringen): ",
                    lambda x: x if x else None)  # Leeren String zu None umwandeln
                input_kontaktdaten_key(
                    kontaktdaten, ["zeitrahmen", "von_uhrzeit"],
                    "> Von Uhrzeit (Leer lassen zum Überspringen): ",
                    lambda x: x if x else None)  # Leeren String zu None umwandeln
                input_kontaktdaten_key(
                    kontaktdaten, ["zeitrahmen", "bis_uhrzeit"],
                    "> Bis Uhrzeit (Leer lassen zum Überspringen): ",
                    lambda x: x if x else None)  # Leeren String zu None umwandeln
                print(
                    "Trage nun die Wochentage ein, an denen die ausgewählten Impftermine liegen dürfen.\n"
                    "Mehrere Wochentage können durch Komma getrennt werden.\n"
                    "Beispiel: Mo, Di, Mi, Do, Fr, Sa, So\n"
                    "Leer lassen, um alle Wochentage auszuwählen.")
                input_kontaktdaten_key(
                    kontaktdaten, ["zeitrahmen", "wochentage"],
                    "> Erlaubte Wochentage: ", parse_wochentage)
            print()

        json.dump(kontaktdaten, file, ensure_ascii=False, indent=4)

    return kontaktdaten


def parse_wochentage(string):
    wochentage = [wt.strip() for wt in string.split(",")]
    # Leere strings durch "if wt" rausfiltern
    nums = [decode_wochentag(wt) for wt in wochentage if wt]
    if not nums:
        # None zurückgeben, damit der Key nicht gesetzt wird.
        # Folglich wird der Default genutzt: Alle Wochentage sind zulässig.
        return None
    nums = sorted(set(nums))
    return [encode_wochentag(num) for num in nums]


def input_kontaktdaten_key(
        kontaktdaten,
        path,
        prompt,
        transformer=lambda x: x):
    target = kontaktdaten
    for key in path[:-1]:
        target = target[key]
    key = path[-1]
    while True:
        try:
            value = transformer(input(prompt).strip())
            # Wenn transformer None zurückgibt, setzen wir den Key nicht.
            if value is not None:
                target[key] = value
                validate_kontaktdaten(kontaktdaten)
            break
        except ValidationError as exc:
            print(f"\n{str(exc)}\n")


def run_search_interactive(kontaktdaten_path, configure_notifications, check_delay):
    """
    Interaktives Setup für die Terminsuche:
    1. Ggf. zuerst Eingabe, ob Kontaktdaten aus kontaktdaten.json geladen
       werden sollen.
    2. Laden der Kontaktdaten aus kontaktdaten.json.
    3. Bei unvollständigen Kontaktdaten: Interaktive Eingabe der fehlenden
       Kontaktdaten.
    4. Terminsuche

    :param kontaktdaten_path: Pfad zur JSON-Datei mit Kontaktdaten. Default: data/kontaktdaten.json im aktuellen Ordner
    :param configure_notifications: Wird durchgereicht zu update_kontaktdaten_interactive()
    """

    print(
        "Bitte trage zunächst deinen Impfcode und deine Kontaktdaten ein.\n"
        f"Die Daten werden anschließend lokal in der Datei '{os.path.basename(kontaktdaten_path)}' abgelegt.\n"
        "Du musst sie zukünftig nicht mehr eintragen.\n")

    kontaktdaten = {}
    if os.path.isfile(kontaktdaten_path):
        daten_laden = input(
            f"> Sollen die vorhandenen Daten aus '{os.path.basename(kontaktdaten_path)}' geladen werden? (y/n): ").lower()
        if daten_laden.lower() != "n":
            kontaktdaten = get_kontaktdaten(kontaktdaten_path)

    print()
    kontaktdaten = update_kontaktdaten_interactive(
        kontaktdaten, "search", configure_notifications, kontaktdaten_path)
    return run_search(kontaktdaten, check_delay)


def run_search(kontaktdaten, check_delay):
    """
    Nicht-interaktive Terminsuche

    :param kontaktdaten: Dictionary mit Kontaktdaten
    """

    try:
        codes = kontaktdaten["codes"]

        # Hinweis, wenn noch alte Version der Kontaktdaten.json verwendet wird
        if kontaktdaten.get("plz"):
            print(
                "ACHTUNG: Du verwendest noch die alte Version der 'Kontaktdaten.json'!\n"
                "Lösche vor dem nächsten Ausführen die Datei und fülle die Kontaktdaten bitte erneut aus.\n")
            plz_impfzentren = [kontaktdaten.get("plz")]
        else:
            plz_impfzentren = kontaktdaten["plz_impfzentren"]

        kontakt = kontaktdaten["kontakt"]
        print(
            f"Kontaktdaten wurden geladen für: {kontakt['vorname']} {kontakt['nachname']}\n")

        notifications = kontaktdaten.get("notifications", {})

        zeitrahmen = kontaktdaten["zeitrahmen"]
    except KeyError as exc:
        raise ValueError(
            "Kontaktdaten konnten nicht aus 'kontaktdaten.json' geladen werden.\n"
            "Bitte überprüfe, ob sie im korrekten JSON-Format sind oder gebe "
            "deine Daten beim Programmstart erneut ein.\n") from exc

    ImpfterminService.terminsuche(
        codes=codes,
        plz_impfzentren=plz_impfzentren,
        kontakt=kontakt,
        notifications=notifications,
        zeitrahmen=zeitrahmen,
        check_delay=check_delay,
        PATH=PATH)


def gen_code_interactive(kontaktdaten_path):
    """
    Interaktives Setup für die Codegenerierung:
    1. Ggf. zuerst Eingabe, ob Kontaktdaten aus kontaktdaten.json geladen
       werden sollen.
    2. Laden der Kontaktdaten aus kontaktdaten.json.
    3. Bei unvollständigen Kontaktdaten: Interaktive Eingabe derjenigen
       fehlenden Kontaktdaten, die für die Codegenerierung benötigt werden.
    4. Codegenerierung

    :param kontaktdaten_path: Pfad zur JSON-Datei mit Kontaktdaten. Default: kontaktdaten.json im aktuellen Ordner
    """

    print(
        "Du kannst dir jetzt direkt einen Vermittlungscode erstellen.\n"
        "Dazu benötigst du eine Mailadresse, Telefonnummer und die PLZ deines Impfzentrums.\n"
        f"Die Daten werden anschließend lokal in der Datei '{os.path.basename(kontaktdaten_path)}' abgelegt.\n"
        "Du musst sie zukünftig nicht mehr eintragen.\n")

    kontaktdaten = {}
    if os.path.isfile(kontaktdaten_path):
        daten_laden = input(
            f"> Sollen die vorhandenen Daten aus '{os.path.basename(kontaktdaten_path)}' geladen werden (y/n)?: ").lower()
        if daten_laden.lower() != "n":
            kontaktdaten = get_kontaktdaten(kontaktdaten_path)

    print()
    kontaktdaten = update_kontaktdaten_interactive(
        kontaktdaten, "code", False, kontaktdaten_path)
    return gen_code(kontaktdaten)


def gen_code(kontaktdaten):
    """
    Codegenerierung ohne interaktive Eingabe der Kontaktdaten

    :param kontaktdaten: Dictionary mit Kontaktdaten
    """

    try:
        plz_impfzentrum = kontaktdaten["plz_impfzentren"][0]
        mail = kontaktdaten["kontakt"]["notificationReceiver"]
        telefonnummer = kontaktdaten["kontakt"]["phone"]
        if not telefonnummer.startswith("+49"):
            telefonnummer = f"+49{remove_prefix(telefonnummer, '0')}"
    except KeyError as exc:
        raise ValueError(
            "Kontaktdaten konnten nicht aus 'kontaktdaten.json' geladen werden.\n"
            "Bitte überprüfe, ob sie im korrekten JSON-Format sind oder gebe "
            "deine Daten beim Programmstart erneut ein.\n") from exc

    its = ImpfterminService([], {}, PATH)

    # Einmal Chrome starten, um früh einen Fehler zu erzeugen, falls die
    # erforderliche Software nicht installiert ist.
    its.log.info("Prüfen von Chromium und Chromedriver")
    its.get_chromedriver(headless=True).quit()

    print("\nBitte trage nachfolgend dein Geburtsdatum im Format DD.MM.YYYY ein.\n"
          "Beispiel: 02.03.1982\n")
    while True:
        try:
            geburtsdatum = input("> Geburtsdatum: ")
            validate_datum(geburtsdatum)
            break
        except ValidationError as exc:
            print("Das Datum entspricht nicht dem richtigen Format (DD.MM.YYYY). "
                  "Bitte erneut versuchen.")

    # code anfordern via selenium
    try:
        if its.selenium_code_anfordern(mail, telefonnummer, plz_impfzentrum, geburtsdatum):
            return True
    except RuntimeError as exc:
        print(
            f"\nDie Code-Generierung war leider nicht erfolgreich:\n{str(exc)}")
        return False

    print("Die Code-Generierung war leider nicht erfolgreich.")
    return False


def subcommand_search(args):
    if args.configure_only:
        update_kontaktdaten_interactive(
            get_kontaktdaten(args.file), "search", args.configure_notifications, args.file)
    elif args.read_only:
        run_search(get_kontaktdaten(args.file), check_delay=args.retry_sec)
    else:
        run_search_interactive(args.file, args.configure_notifications, check_delay=args.retry_sec)


def subcommand_code(args):
    if args.configure_only:
        update_kontaktdaten_interactive(
            get_kontaktdaten(args.file), "code", args.configure_notifications, args.file)
    elif args.read_only:
        gen_code(get_kontaktdaten(args.file))
    else:
        gen_code_interactive(args.file)


def subcommand_install_chromium():
    # Mac_Arm currently not working
    if current_platform() == 'mac-arm':
        print('Zur Zeit kann keine eigene Chromium Instanz auf einem Mac M1 installiert werden.')
    else:
        if not check_chromium():
            download_chromium()
        else:
            print('Eigene Chromium Instanz bereits installiert.')
        if not check_webdriver():
            download_webdriver()


def validate_args(args):
    """
    Raises ValueError if args contain invalid settings.
    """

    if args.configure_only and args.read_only:
        raise ValueError(
            "--configure-only und --read-only kann nicht gleichzeitig verwendet werden")


def main():
    create_missing_dirs(PATH)

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help="commands", dest="command")

    base_subparser = argparse.ArgumentParser(add_help=False)
    base_subparser.add_argument(
        "-f",
        "--file",
        help="Pfad zur JSON-Datei für Kontaktdaten")
    base_subparser.add_argument(
        "-c",
        "--configure-only",
        action='store_true',
        help="Nur Kontaktdaten erfassen und in JSON-Datei abspeichern")
    base_subparser.add_argument(
        "-r",
        "--read-only",
        action='store_true',
        help="Es wird nicht nach fehlenden Kontaktdaten gefragt. Stattdessen wird ein Fehler angezeigt, falls benötigte Kontaktdaten in der JSON-Datei fehlen.")
    base_subparser.add_argument(
        "-n",
        "--configure-notifications",
        action='store_true',
        help="Gibt bei der Erfassung der Kontaktdaten die Möglichkeit, Benachrichtungen über Pushover und Telegram zu konfigurieren.")

    parser_search = subparsers.add_parser(
        "search", parents=[base_subparser], help="Termin suchen")
    parser_search.add_argument(
        "-s",
        "--retry-sec",
        type=int,
        default=60,
        help="Wartezeit zwischen zwei Versuchen (in Sekunden)")

    parser_code = subparsers.add_parser(
        "code",
        parents=[base_subparser],
        help="Vermittlungscode generieren")

    args = parser.parse_args()

    if not hasattr(args, "file") or args.file is None:
        args.file = os.path.join(PATH, "data/kontaktdaten.json")
    if not hasattr(args, "configure_only"):
        args.configure_only = False
    if not hasattr(args, "read_only"):
        args.read_only = False
    if not hasattr(args, "retry_sec"):
        args.retry_sec = 60
    if not hasattr(args, "configure_notifications"):
        args.configure_notifications = False

    try:
        validate_args(args)
    except ValueError as exc:
        parser.error(str(exc))
        # parser.error terminates the program with status code 2.

    if args.command is not None:
        try:
            if args.command == "search":
                subcommand_search(args)
            elif args.command == "code":
                subcommand_code(args)
            else:
                assert False
        except ValidationError as exc:
            print(f"Fehler in {json.dumps(args.file)}:\n{str(exc)}")

    else:
        extended_settings = False

        while True:
            print(
                "Was möchtest du tun?\n"
                "[1] Termin suchen\n"
                "[2] Vermittlungscode generieren\n"
                "[3] Eigene Chromium Instanz im Vaccipy Ordner installieren\n"
                f"[x] Erweiterte Einstellungen {'verbergen' if extended_settings else 'anzeigen'}\n")

            if extended_settings:
                print(
                    f"[c] --configure-only {'de' if args.configure_only else ''}aktivieren\n"
                    f"[r] --read-only {'de' if args.read_only else ''}aktivieren\n"
                    "[s] --retry-sec setzen\n"
                    f"[n] --configure-notifications {'de' if args.configure_notifications else ''}aktivieren\n\n")

            option = input("> Option: ").lower()
            print()

            try:
                if option == "1":
                    subcommand_search(args)
                elif option == "2":
                    subcommand_code(args)
                elif option == "3":
                    subcommand_install_chromium()
                elif option == "x":
                    extended_settings = not extended_settings
                elif extended_settings and option == "c":
                    new_args = copy.copy(args)
                    new_args.configure_only = not new_args.configure_only
                    validate_args(new_args)
                    args = new_args
                    print(
                        f"--configure-only {'de' if not args.configure_only else ''}aktiviert.")
                elif extended_settings and option == "r":
                    new_args = copy.copy(args)
                    new_args.read_only = not new_args.read_only
                    validate_args(new_args)
                    args = new_args
                    print(
                        f"--read-only {'de' if not args.read_only else ''}aktiviert.")
                elif extended_settings and option == "s":
                    args.retry_sec = int(input("> --retry-sec="))
                    if args.retry_sec<30:
                        print("[RETRY-SEC] Um die Server nicht übermäßig zu belasten, wurde der Wert auf 30 Sekunden gesetzt")
                        args.retry_sec = 30
                elif extended_settings and option == "n":
                    new_args = copy.copy(args)
                    new_args.configure_notifications = not new_args.configure_notifications
                    validate_args(new_args)
                    args = new_args
                    print(
                        f"--configure-notifications {'de' if not args.configure_notifications else ''}aktiviert.")
                else:
                    print("Falscheingabe! Bitte erneut versuchen.")
                print()
            except TypeError as exc:
                if str(exc) == "expected str, bytes or os.PathLike object, not NoneType":
                    print("\nChromium nicht gefunden. Drei Möglichkeiten zur Problembehebung:\n"
                          "1) Google Chrome installieren: https://www.google.com/intl/de_de/chrome/\n"
                          "2) Chromium über das Vaccipy-Menü installieren: "
                          "'[3] Eigene Chromium Instanz im Vaccipy Ordner installieren'\n"
                          "3) Pfad für Chromium und Chromedriver über Umgebungsvariablen festlegen: "
                          "VACCIPY_CHROME_BIN (Chromium) und VACCIPY_CHROMEDRIVER (Chromedriver)\n")
                else:
                    print(f"\nUnbekannter TypeError:\n{str(exc)}\n")
            except Exception as exc:
                print(f"\nFehler:\n{str(exc)}\n")


if __name__ == "__main__":
    print("""
                                _
                               (_)
 __   __   __ _    ___    ___   _   _ __    _   _
 \ \ / /  / _` |  / __|  / __| | | | '_ \  | | | |
  \ V /  | (_| | | (__  | (__  | | | |_) | | |_| |
   \_/    \__,_|  \___|  \___| |_| | .__/   \__, |
                                   | |       __/ |
                                   |_|      |___/
""")

    # Auf aktuelle Version prüfen
    try:
        if not update_available():
            print('Du verwendest die aktuellste Version von vaccipy: ' + get_current_version())
        else:
            print("Du verwendest eine alte Version von vaccipy.\n"
                  "Bitte installiere die aktuellste Version. Link zum Download:\n"
                  "https://github.com/iamnotturner/vaccipy/releases/tag/" + get_latest_version())
    except:
        print("vaccipy konnte nicht auf die neuste Version geprüft werden.")

    print()
    print("Automatische Terminbuchung für den Corona Impfterminservice\n")

    print("Vor der Ausführung des Programms ist die Berechtigung zur Impfung zu prüfen.\n"
          "Ob Anspruch auf eine Impfung besteht, kann hier nachgelesen werden:\n"
          "https://www.impfterminservice.de/terminservice/faq\n")
    main()
