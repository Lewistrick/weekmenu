"""Build Dutch catalog from translations.xlsx with auto-fill for missing rows."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.i18n.catalog_en import TEXTS as EN_TEXTS
from src.i18n.icons import strip_icons

XLSX = ROOT / "translations.xlsx"
OUT = ROOT / "src" / "i18n" / "catalog_nl.py"

# Dutch translations for keys missing from the spreadsheet.
AUTO_NL: dict[str, str] = {
    "auth.field.confirm_password": "Bevestig wachtwoord",
    "common.aria.recipe_metadata": "receptmetadata",
    "common.aria.recipe_tags": "recepttags",
    "common.empty.no_tag_groups": "Nog geen taggroepen. Voeg ze toe op de pagina Taggroepen.",
    "common.empty.no_tag_groups_short": "Nog geen taggroepen.",
    "common.placeholder.search_recipe": "Naam, beschrijving of ingrediënt…",
    "common.status.disabled": "Uitgeschakeld",
    "common.status.enabled": "Ingeschakeld",
    "common.status.private": "Privé",
    "common.status.public": "Openbaar",
    "grocery.aria.actions_for_item": "Acties voor {item_name}",
    "grocery.aria.already_have": "Heb ik al",
    "grocery.aria.edit_amount": "Hoeveelheid bewerken",
    "grocery.aria.edit_amount_for": "Hoeveelheid bewerken voor {item_name}",
    "grocery.aria.move_to_to_check": "Verplaats naar te controleren",
    "grocery.aria.quantity_for": "Hoeveelheid voor {item_name}",
    "grocery.aria.remove_from_already_have": "Verwijder uit heb ik al",
    "grocery.aria.remove_from_to_check": "Verwijder uit te controleren",
    "grocery.aria.save_amount": "Hoeveelheid opslaan",
    "grocery.aria.unit_for": "Eenheid voor {item_name}",
    "grocery.action.add_weekly_groceries": "🧺 Wekelijkse boodschappen toevoegen",
    "grocery.action.mark_all": "Alles afvinken",
    "grocery.action.mark_all.confirm": "Alles afvinken?",
    "grocery.already_have.empty": "Nog niets gemarkeerd als al in huis.",
    "grocery.back_to_week_menu": "← Terug naar weekmenu",
    "grocery.by_shop.empty": "Wijs ingrediënten toe aan een winkel om hier je lijsten op te bouwen.",
    "grocery.clear_list": "Lijst wissen",
    "grocery.clear_list.confirm": "Lijst wissen?",
    "grocery.copy.title": "Kopiëren voor berichten",
    "grocery.empty": "Nog geen ingrediënten. Genereer een lijst vanuit je weekmenu, voeg hierboven je eigen boodschappen toe, of voeg je wekelijkse boodschappen toe.",
    "grocery.generate.action": "Boodschappenlijst genereren",
    "grocery.generate.add": "➕ Toevoegen",
    "grocery.generate.add.aria": "Toevoegen aan lijst",
    "grocery.generate.add.title": "Weekmenu-boodschappen toevoegen aan huidige lijst",
    "grocery.generate.aria": "Boodschappenlijst genereren",
    "grocery.generate.confirm": "Boodschappenlijst bijwerken?",
    "grocery.generate.replace": "🔄 Vervangen",
    "grocery.generate.replace.aria": "Lijst vervangen",
    "grocery.generate.replace.title": "Lijst vervangen door weekmenu-boodschappen",
    "grocery.label.to_check": "Te controleren",
    "grocery.label.unassigned": "Niet toegewezen",
    "grocery.lead": "Sorteer ingrediënten links per winkel en bekijk je lijsten rechts.",
    "grocery.section.add_groceries": "Boodschappen toevoegen",
    "grocery.section.already_have": "Heb ik al",
    "grocery.section.by_shop": "Per winkel",
    "grocery.section.to_check": "Te controleren",
    "grocery.section.to_sort": "Te sorteren",
    "grocery.to_check.empty": "Niets gemarkeerd om later te controleren.",
    "grocery.to_sort.empty": "Alles is gesorteerd, gecontroleerd of al in huis.",
    "ingredient.action.add": "Toevoegen",
    "ingredient.action.remove_line": "Verwijderen",
    "ingredient.aria.add": "Ingrediënt toevoegen",
    "ingredient.aria.cancel_edit": "Bewerken annuleren",
    "ingredient.aria.edit": "Ingrediënt bewerken",
    "ingredient.aria.remove": "Ingrediënt verwijderen",
    "ingredient.placeholder.name": "Naam",
    "ingredient.placeholder.quantity": "Hoeveelheid",
    "ingredient.placeholder.unit": "Eenheid",
    "message.auth.current_password_incorrect": "Huidig wachtwoord is onjuist.",
    "message.auth.email_updated": "E-mailadres bijgewerkt.",
    "message.auth.invalid_credentials": "Ongeldige gebruikersnaam of wachtwoord.",
    "message.auth.new_password_min_length": "Nieuw wachtwoord moet minstens {min} tekens zijn.",
    "message.auth.new_passwords_no_match": "Nieuwe wachtwoorden komen niet overeen.",
    "message.auth.password_changed": "Wachtwoord gewijzigd.",
    "message.auth.password_min_length": "Wachtwoord moet minstens {min} tekens zijn.",
    "message.auth.passwords_no_match": "Wachtwoorden komen niet overeen.",
    "message.auth.settings_updated": "Instellingen bijgewerkt.",
    "message.auth.username_required": "Gebruikersnaam is verplicht.",
    "message.auth.username_taken": "Die gebruikersnaam is al in gebruik.",
    "message.recipe.added_to_week_menu": "Toegevoegd aan weekmenu: {day}",
    "message.recipe.all_days_pinned": "Alle dagen zijn vastgezet. Maak minstens één dag los voordat je een recept toevoegt.",
    "message.recipe.already_imported": "Je hebt dit recept al geïmporteerd.",
    "message.recipe.deleted": "Recept verwijderd: {name}",
    "message.recipe.description_not_saved": "Geen receptbeschrijving gevonden, niet opgeslagen.",
    "message.recipe.description_updated": "Receptbeschrijving bijgewerkt",
    "message.recipe.error": "Fout: {error}",
    "message.recipe.ingredient_added": "Ingrediënt toegevoegd",
    "message.recipe.ingredient_duplicate": "Ingrediënt staat al in het recept. Niet opgeslagen.",
    "message.recipe.ingredient_duplicate_edit": "Ingrediënt staat al in het recept. Bewerk het bestaande ingrediënt.",
    "message.recipe.ingredient_not_added": "Ingrediënt niet toegevoegd: {name} (eenheid niet gevonden: {unit})",
    "message.recipe.ingredient_updated": "Ingrediënt bijgewerkt",
    "message.recipe.invalid_quantity": "Ongeldige hoeveelheid, niet opgeslagen.",
    "message.recipe.name_not_saved": "Geen receptnaam gevonden, niet opgeslagen.",
    "message.recipe.name_updated": "Receptnaam bijgewerkt",
    "message.recipe.new_ingredient": "Hé, {name} kende ik nog niet!",
    "message.recipe.no_ingredient_name": "Geen ingrediëntnaam gevonden, niet opgeslagen.",
    "message.recipe.no_ingredient_selected": "Geen ingrediënt geselecteerd.",
    "message.recipe.no_quantity": "Geen hoeveelheid gevonden, niet opgeslagen.",
    "message.recipe.no_quantity_provided": "Geen hoeveelheid opgegeven.",
    "message.recipe.no_unit": "Geen eenheid gevonden, niet opgeslagen.",
    "message.recipe.no_unit_selected": "Geen eenheid geselecteerd.",
    "message.recipe.tags_updated": "Recepttags bijgewerkt",
    "message.recipe.unit_not_found": "Eenheid niet gevonden, niet opgeslagen.",
    "message.recipe.unit_not_found_named": "Eenheid niet gevonden: {unit}",
    "message.shops.added": "Winkel toegevoegd.",
    "message.shops.already_exists": "Die winkel bestaat al.",
    "message.shops.assignment_saved": "Toewijzing opgeslagen.",
    "message.shops.deleted": "Winkel verwijderd.",
    "message.shops.ingredient_deleted": "Ingrediënt verwijderd.",
    "message.shops.name_in_use": "Die winkelnaam is al in gebruik.",
    "message.shops.name_required": "Winkelnaam is verplicht.",
    "message.shops.updated": "Winkel bijgewerkt.",
    "message.tags.group_added": "Taggroep toegevoegd: {name}",
    "message.tags.group_delete_has_tags": "Kan taggroep '{name}' niet verwijderen zolang er nog tags in zitten.",
    "message.tags.group_deleted": "Taggroep verwijderd: {name}",
    "message.tags.group_exists": "Taggroep bestaat al: {name}",
    "message.tags.group_name_required": "Naam van taggroep is verplicht.",
    "message.tags.group_renamed": "Taggroep bijgewerkt naar: {name}",
    "message.tags.tag_added": "Tag '{tag}' toegevoegd aan {group}.",
    "message.tags.tag_deleted": "Tag verwijderd: {name}",
    "message.tags.tag_exists": "Tag '{tag}' bestaat al in {group}.",
    "message.tags.tag_name_required": "Tagnaam is verplicht.",
    "message.tags.tag_renamed": "Tag bijgewerkt naar: {name}",
    "message.units.abbrev_required": "Afkorting is verplicht.",
    "message.units.added": "Eenheid toegevoegd.",
    "message.units.deleted": "Eenheid verwijderd.",
    "message.units.in_use": "Kan '{abbrev}' niet verwijderen zolang het in recepten of lijsten wordt gebruikt.",
    "message.units.not_found": "Eenheid niet gevonden.",
    "message.units.updated": "Eenheid bijgewerkt.",
    "message.week_menu.added_grocery": "{name} toegevoegd aan je boodschappenlijst.",
    "message.week_menu.all_days_pinned_randomize": "Alle dagen zijn vastgezet. Maak minstens één dag los om te randomiseren.",
    "message.week_menu.added_weekly_groceries": "{count} wekelijkse {noun} toegevoegd aan je boodschappenlijst.",
    "message.week_menu.combined_existing": "Samengevoegd met bestaande {name} ({unit}).",
    "message.week_menu.constraint_select_tag": "Selecteer een tag voor elke actieve tagbeperking voordat je randomiseert.",
    "message.week_menu.constraint_unsatisfied": "Kon geen weekmenu maken dat aan de geselecteerde tagbeperkingen voldoet.",
    "message.week_menu.enter_ingredient": "Voer een ingrediëntnaam in.",
    "message.week_menu.enter_positive_amount": "Voer een positieve hoeveelheid in.",
    "message.week_menu.grocery_preserved": "Je boodschappenlijst is bewaard en niet opnieuw gegenereerd vanuit het weekmenu.",
    "message.week_menu.no_weekly_groceries": "Je hebt nog geen wekelijkse boodschappen. Voeg ze eerst toe via Instellingen.",
    "message.week_menu.noun_groceries": "boodschappen",
    "message.week_menu.noun_grocery": "boodschap",
    "message.week_menu.weekly_already_on_list": "Je wekelijkse boodschappen staan al op de boodschappenlijst.",
    "message.weekly_groceries.added": "Wekelijkse boodschap toegevoegd.",
    "message.weekly_groceries.already_exists": "Die wekelijkse boodschap bestaat al.",
    "message.weekly_groceries.deleted": "Wekelijkse boodschap verwijderd.",
    "message.weekly_groceries.ingredient_required": "Ingrediëntnaam is verplicht.",
    "message.weekly_groceries.not_found": "Wekelijkse boodschap niet gevonden.",
    "message.weekly_groceries.positive_amount": "Voer een positieve hoeveelheid in.",
    "message.weekly_groceries.unit_not_found": "Eenheid niet gevonden: {unit}",
    "message.weekly_groceries.unit_required": "Een eenheid is verplicht.",
    "message.weekly_groceries.updated": "Wekelijkse boodschap bijgewerkt.",
    "profile.action.change_password": "Wachtwoord wijzigen",
    "profile.action.delete_account": "Account verwijderen",
    "profile.action.save_email": "E-mailadres opslaan",
    "profile.action.save_settings": "Instellingen opslaan",
    "profile.confirm.delete_account": "Je account en al je recepten verwijderen? Dit kan niet ongedaan worden gemaakt.",
    "profile.field.confirm_new_password": "Bevestig nieuw wachtwoord",
    "profile.field.current_password": "Huidig wachtwoord",
    "profile.field.default_servings": "Standaard porties weekmenu",
    "profile.field.language": "Taal",
    "profile.field.new_password": "Nieuw wachtwoord",
    "profile.lead": "Beheer je accountgegevens.",
    "profile.section.change_password": "Wachtwoord wijzigen",
    "profile.section.danger_zone": "Gevarenzone",
    "profile.section.details": "Gegevens",
    "profile.section.settings": "Instellingen",
    "profile.username_label": "Gebruikersnaam:",
    "recipe.add.action.add_ingredient": "+ Ingrediënt toevoegen",
    "recipe.add.ingredients_hint": "Voeg per regel hoeveelheid, eenheid en ingrediëntnaam toe.",
    "recipe.add.lead": "Vul de gegevens hieronder in. Je kunt ingrediënten één voor één toevoegen.",
    "recipe.add.submit": "Recept toevoegen",
    "recipe.add.success": "Recept {recipe_name} succesvol toegevoegd.",
    "recipe.add.tags_hint": "Selecteer tagwaarden die dit recept beschrijven.",
    "recipe.add.view_recipe": "Recept bekijken",
    "recipe.delete.click_here": "klik hier.",
    "recipe.delete.confirm_before": "Als je zeker weet dat je het recept wilt verwijderen,",
    "recipe.delete.confirm_prompt": "Als je zeker weet dat je het recept wilt verwijderen, klik hier.",
    "recipe.edit.action.delete": "🗑️ Recept verwijderen",
    "recipe.edit.action.edit_description": "✏️ Beschrijving bewerken",
    "recipe.edit.action.edit_title": "✏️ Titel bewerken",
    "recipe.edit.action.edit_title_plain": "Titel bewerken",
    "recipe.edit.action.save_description": "Beschrijving opslaan",
    "recipe.edit.action.save_tags": "💾 Tags opslaan",
    "recipe.edit.action.save_title": "Titel opslaan",
    "recipe.edit.aria.delete_recipe": "Recept verwijderen",
    "recipe.edit.aria.edit_description": "Beschrijving bewerken",
    "recipe.edit.aria.edit_title": "Titel bewerken",
    "recipe.edit.aria.save_tags": "Tags opslaan",
    "recipe.edit.aria.view_recipe": "Recept bekijken",
    "recipe.edit.back_to_view": "← Recept bekijken",
    "recipe.edit.delete_hint": "Dit verwijdert het recept en alle ingrediëntregels permanent.",
    "recipe.edit.description_hint": "Klik op Beschrijving bewerken om de bereidingsstappen aan te passen.",
    "recipe.edit.ingredients_hint": "Gebruik Bewerken of Verwijderen op elke regel, of voeg hieronder een nieuw ingrediënt toe.",
    "recipe.edit.mode_badge": "Bewerkmodus",
    "recipe.edit.section.delete": "Recept verwijderen",
    "recipe.edit.section.description": "Beschrijving",
    "recipe.edit.section.status": "Status",
    "recipe.edit.section.title": "Titel",
    "recipe.edit.status_hint": "Schakel zichtbaarheid en of dit recept in menu's wordt gebruikt.",
    "recipe.edit.tags_hint": "Werk tagwaarden bij voor zoeken en filteren.",
    "recipe.edit.title_hint": "Klik op Titel bewerken om dit recept te hernoemen.",
    "recipe.field.cook_time_minutes": "Kooktijd (minuten)",
    "recipe.field.name": "Receptnaam",
    "recipe.field.prep_time_minutes": "Bereidingstijd (minuten)",
    "recipe.status.enabled_recipe": "Recept ingeschakeld",
    "recipe.status.public_recipe": "Openbaar recept",
    "recipe.view.action.add_to_week_menu": "🗓️ Toevoegen aan weekmenu",
    "recipe.view.action.edit": "✏️ Recept bewerken",
    "recipe.view.action.import": "📥 Importeren naar mijn recepten",
    "recipe.view.already_imported": "Al in je collectie",
    "recipe.view.by_owner": "Door {username}",
    "recipe.view.created_by": "Gemaakt door {username}",
    "recipe.view.title_with_id": "#{recipe_id} {recipe_name}",
    "recipes_missing_tags.aria.add_to_week_menu": "Toevoegen aan weekmenu",
    "recipes_missing_tags.aria.edit": "Recept bewerken",
    "recipes_missing_tags.aria.view": "Recept bekijken",
    "recipes_missing_tags.empty": "Elk recept heeft minstens één tag in elke taggroep.",
    "recipes_missing_tags.lead": "Vind recepten die in één of meer taggroepen tags missen en los dat snel op.",
    "recipes_missing_tags.missing_groups": "Ontbrekende groepen:",
    "search.filter_by_tags": "Filteren op tags",
    "search.filter_hint": "Recepten zonder tag in een groep blijven altijd meegerekend voor die groep.",
    "search.lead": "Doorzoek je kookboek op naam, beschrijving of ingrediënt.",
    "search.placeholder.waiting": "Resultaten verschijnen hier terwijl je typt.",
    "search.results.empty": "Geen recepten gevonden voor je zoekopdracht.",
    "search.results.title": "Zoekresultaten",
    "shops.aria.add_shop": "Winkel toevoegen",
    "shops.aria.delete_shop": "Winkel verwijderen",
    "shops.aria.save_shop": "Winkel opslaan",
    "shops.assignments.aria.delete_unused": "Ongebruikt ingrediënt verwijderen",
    "shops.assignments.aria.shop_for": "Winkel voor {ingredient_name}",
    "shops.assignments.aria.unassigned": "Niet toegewezen",
    "shops.assignments.empty": "Nog geen ingrediënten. Voeg eerst recepten met ingrediënten toe.",
    "shops.assignments.hint": "Wijs ingrediënten hier opnieuw toe. De boodschappenlijst wijst alleen een winkel toe als er nog geen is ingesteld.",
    "shops.assignments.in_recipes": "in {count} recept(en)",
    "shops.assignments.title": "Ingrediënttoewijzingen",
    "shops.assignments.unassigned": "Niet toegewezen",
    "shops.empty": "Nog geen winkels.",
    "shops.lead": "Maak winkels aan, stel hun kleuren in en wijs ingrediënten opnieuw toe.",
    "shops.placeholder.shop_name": "bijv. Albert Heijn",
    "shops.section.add_shop": "Winkel toevoegen",
    "shops.section.existing_shops": "Bestaande winkels",
    "tags.aria.add_group": "Groep toevoegen",
    "tags.aria.add_tag": "Tag toevoegen",
    "tags.aria.delete_group": "Groep verwijderen",
    "tags.aria.delete_tag": "Tag verwijderen",
    "tags.aria.rename_group": "Groep hernoemen",
    "tags.aria.rename_tag": "Tag hernoemen",
    "tags.field.group_name": "Groepsnaam",
    "tags.field.new_value": "Nieuwe waarde",
    "tags.field.tag": "Tag",
    "tags.lead": "Maak taggroepen en waarden aan voor het categoriseren van recepten.",
    "tags.placeholder.group_name": "bijv. seizoen",
    "tags.placeholder.tag_name": "bijv. zomer",
    "tags.section.add_group": "Taggroep toevoegen",
    "tags.section.existing_groups": "Bestaande groepen",
    "units.aria.abbreviation": "Afkorting",
    "units.aria.abbreviation_for": "Afkorting voor {abbrev}",
    "units.aria.add_unit": "Eenheid toevoegen",
    "units.aria.plural_for": "Meervoud voor {abbrev}",
    "units.aria.plural_label": "Meervoud",
    "units.aria.singular_for": "Enkelvoud voor {abbrev}",
    "units.aria.singular_label": "Enkelvoud",
    "units.empty": "Nog geen eenheden.",
    "units.lead": "Beheer meeteenheden voor recepten en boodschappenlijsten. Elke eenheid heeft een afkorting, enkelvoud en meervoud.",
    "units.placeholder.abbrev": "Afk.",
    "units.placeholder.plural": "Meervoud",
    "units.placeholder.singular": "Enkelvoud",
    "units.section.add": "Eenheid toevoegen",
    "units.section.yours": "Jouw eenheden",
    "week_menu.action.randomize": "🎲 Week randomiseren",
    "week_menu.constraint.aria.minimum_days": "Minimum aantal dagen met tag voor {group_name}",
    "week_menu.constraint.aria.minimum_for_group": "Minimum aantal voor {group_name}",
    "week_menu.constraint.aria.tag_for_group": "Tag voor {group_name}",
    "week_menu.constraint.choose_tag": "Kies tag",
    "week_menu.constraint.ignore": "Negeren",
    "week_menu.constraint.minimum": "Minstens N met tag",
    "week_menu.constraint.same_tag": "Overal dezelfde tag",
    "week_menu.constraint.vary": "Afwisselen over de week",
    "week_menu.constraints.hint": "Optionele regels voor randomiseren. Vastgezette dagen tellen mee voor beperkingen.",
    "week_menu.constraints.manage_button": "Beheer beperkingen",
    "week_menu.constraints.none_active": "Geen actieve beperkingen.",
    "week_menu.constraints.title": "Weekmenu-randomiseringsopties",
    "week_menu.day.aria.clear": "Recept van dag wissen",
    "week_menu.day.aria.move_down": "Verplaats {day_label} omlaag",
    "week_menu.day.aria.move_down_short": "Omlaag",
    "week_menu.day.aria.move_up": "Verplaats {day_label} omhoog",
    "week_menu.day.aria.move_up_short": "Omhoog",
    "week_menu.day.aria.search": "Recept zoeken",
    "week_menu.day.aria.servings_for": "Porties voor {day_label}",
    "week_menu.day.no_recipe": "Geen recept gekozen",
    "week_menu.day.pin": "Dag vastzetten",
    "week_menu.day.search_label": "Recept zoeken",
    "week_menu.day.unpin": "Dag losmaken",
    "week_menu.lead": "Plan het avondeten voor de week. Zet dagen vast die je wilt houden, randomiseer de rest, of zoek zelf recepten.",
    "week_menu.start_week_on": "Week starten op",
    "weekly_groceries.aria.add": "Wekelijkse boodschap toevoegen",
    "weekly_groceries.aria.delete": "Verwijderen",
    "weekly_groceries.aria.save": "Opslaan",
    "weekly_groceries.back_to_grocery_list": "🛒 Terug naar boodschappenlijst",
    "weekly_groceries.empty": "Nog geen wekelijkse boodschappen. Voeg hierboven je vaste boodschappen toe.",
    "weekly_groceries.lead": "Houd een lijst bij van boodschappen die je elke week koopt en voeg ze in één klik toe aan een boodschappenlijst.",
    "weekly_groceries.section.add": "Wekelijkse boodschap toevoegen",
    "weekly_groceries.section.yours": "Jouw wekelijkse boodschappen",
    "app.title.manage_week_menu_constraints": "Beheer tagbeperkingen",
    "nav.week_menu_constraints": "Weekmenu beperkingen",
}


def _clean_spreadsheet_text(text: str) -> str:
    """Remove corrupted emoji placeholders from spreadsheet exports."""
    return re.sub(r"^\?+\s*", "", text)


def is_empty(val: object) -> bool:
    if pd.isna(val):
        return True
    s = str(val).strip()
    return s == "" or s.lower() == "nan"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_texts() -> dict[str, str]:
    """Merge spreadsheet Dutch with auto translations and validate keys."""
    df = pd.read_excel(XLSX)
    texts: dict[str, str] = {}
    for _, row in df.iterrows():
        key = str(row["key"]).strip()
        if is_empty(row["Dutch"]):
            if key not in AUTO_NL:
                raise KeyError(f"Missing Dutch for key: {key}")
            raw = AUTO_NL[key]
        else:
            raw = str(row["Dutch"]).strip()
        texts[key] = strip_icons(key, _clean_spreadsheet_text(raw))

    missing_keys = set(EN_TEXTS) - set(texts)
    extra_keys = set(texts) - set(EN_TEXTS)
    if missing_keys:
        raise ValueError(f"Missing keys in Dutch catalog: {sorted(missing_keys)}")
    if extra_keys:
        raise ValueError(f"Extra keys in Dutch catalog: {sorted(extra_keys)}")
    return texts


def write_catalog(texts: dict[str, str]) -> None:
    """Write catalog_nl.py with grouped sections."""
    lines = [
        '"""Dutch UI text catalog keyed for database seeding."""',
        "",
        "TEXTS: dict[str, str] = {",
    ]
    current_section = ""
    for key in sorted(texts, key=lambda k: list(EN_TEXTS.keys()).index(k)):
        section = key.split(".", 1)[0]
        if section != current_section:
            lines.append(f"    # {section}")
            current_section = section
        lines.append(f'    "{key}": "{_escape(texts[key])}",')
    lines.append("}")
    lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    texts = build_texts()
    write_catalog(texts)
    print(f"Wrote {len(texts)} Dutch strings to {OUT}")


if __name__ == "__main__":
    main()
