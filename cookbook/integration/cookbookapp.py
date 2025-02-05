import base64
import gzip
import json
import re
from gettext import gettext as _
from io import BytesIO

import requests
import validators
import yaml

from cookbook.helper.ingredient_parser import IngredientParser
from cookbook.helper.recipe_url_import import (get_from_scraper, get_images_from_soup,
                                               iso_duration_to_minutes)
from cookbook.helper.scrapers.scrapers import text_scraper
from cookbook.integration.integration import Integration
from cookbook.models import Ingredient, Keyword, Recipe, Step


class CookBookApp(Integration):

    def import_file_name_filter(self, zip_info_object):
        return zip_info_object.filename.endswith('.html')

    def get_recipe_from_file(self, file):
        recipe_html = file.getvalue().decode("utf-8")

        # recipe_json, recipe_tree, html_data, images = get_recipe_from_source(recipe_html, 'CookBookApp', self.request)
        scrape = text_scraper(text=recipe_html)
        recipe_json = get_from_scraper(scrape, self.request)
        images = list(dict.fromkeys(get_images_from_soup(scrape.soup, None)))

        recipe = Recipe.objects.create(
            name=recipe_json['name'].strip(),
            created_by=self.request.user, internal=True,
            space=self.request.space)

        try:
            recipe.servings = re.findall('([0-9])+', recipe_json['recipeYield'])[0]
        except Exception as e:
            pass

        try:
            recipe.working_time = iso_duration_to_minutes(recipe_json['prepTime'])
            recipe.waiting_time = iso_duration_to_minutes(recipe_json['cookTime'])
        except Exception:
            pass

        # assuming import files only contain single step
        step = Step.objects.create(instruction=recipe_json['steps'][0]['instruction'], space=self.request.space, show_ingredients_table=self.request.user.userpreference.show_step_ingredients, )

        if 'nutrition' in recipe_json:
            step.instruction = step.instruction + '\n\n' + recipe_json['nutrition']

        step.save()
        recipe.steps.add(step)

        ingredient_parser = IngredientParser(self.request, True)
        for ingredient in recipe_json['steps'][0]['ingredients']:
            f = ingredient_parser.get_food(ingredient['food']['name'])
            u = None
            if unit := ingredient.get('unit', None):
                u = ingredient_parser.get_unit(unit.get('name', None))
            step.ingredients.add(Ingredient.objects.create(
                food=f, unit=u, amount=ingredient.get('amount', None), note=ingredient.get('note', None),  original_text=ingredient.get('original_text', None), space=self.request.space,
            ))

        if len(images) > 0:
            try:
                url = images[0]
                if validators.url(url, public=True):
                    response = requests.get(url)
                    self.import_recipe_image(recipe, BytesIO(response.content))
            except Exception as e:
                print('failed to import image ', str(e))

        recipe.save()
        return recipe
