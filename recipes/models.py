from django.db import models
from django.db.models import F
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.core.urlresolvers import reverse
from django.forms import ModelForm, Textarea
import datetime, decimal, fractions
import sys

UNIT_CHOICES = (
    (u'cup', u'cup'),
    (u'tbs', u'tablespoon'),
    (u'tsp', u'teaspoon'),
    (u'lb', u'pound'),
    (u'oz', u'ounce'),
    (u'box', u'box'),
    (u'pkg', u'package'),
    (u'can', u'can'),
    (u'oth', u'to taste'),
    (u'itm', u'item'),
    (u'qrt', u'quart'),
    (u'foz', u'fluid ounce'),
    )

UNIT_CONVERSIONS = {
    (u'cup',u'tbs'):16,
    (u'tbs',u'tsp'):3,
    (u'qrt',u'cup'):4,
    (u'cup',u'tsp'):48,
    (u'cup',u'foz'):8,
    (u'lb',u'oz'):16,
    (u'oth',u'tsp'):1,
}

def convert(unit_a,unit_b):
    if (unit_a,unit_b) in UNIT_CONVERSIONS:
        return UNIT_CONVERSIONS[(unit_a,unit_b)]
    elif (unit_b,unit_a) in UNIT_CONVERSIONS:
        return decimal.Decimal(str(1.0/UNIT_CONVERSIONS[(unit_b,unit_a)]))
    else:
        return 0 #should raise an exception

DISH_CHOICES = (
    (u'apptz', u'Appetizer'),
    (u'brd',u'Bread'),
    (u'bkfst', u'Breakfast'),
    (u'duov', u'Dutch Oven'),
    (u'dsrt', u'Dessert'),
    (u'main', u'Entree'),
    (u'salad', u'Salad'),
    (u'sdwch', u'Sandwich'),
    (u'side', u'Side Dish'),
    (u'snack', u'Snack'),
    (u'soup', u'Soup'),
    (u'oth',u'Other'),
    )

DEPT_CHOICES = (
    (u'bkry', u'Bakery'),
    (u'drygd', u'Dry Goods'),
    (u'dairy', u'Dairy'),
    (u'deli', u'Delicatessan'),
    (u'frzn', u'Frozen'),
    (u'prdc', u'Produce'),
    (u'meat', u'Meat and Fish'),
    (u'juice', u'Drinks '),
    (u'canned', u'Canned Goods'),
    (u'spice', u'Spices, Condiments, Sauces'),
    )

class Recipe(models.Model):
    name = models.CharField(max_length=100)
    date_added = models.DateTimeField('date added', auto_now_add=True)
    origin = models.CharField(max_length=200, blank=True)
    cooking_time = models.PositiveIntegerField('cook time',blank=True, null=True)
    prep_time = models.PositiveIntegerField('prep time', blank=True, null=True)
    slug = models.SlugField(unique=True)
    notes = models.TextField(blank=True)
    dish = models.CharField(max_length=6, choices=DISH_CHOICES)
    servings = models.PositiveIntegerField('number of servings',default=4)
    image_url = models.URLField(blank=True)


    def nutrition(self):
        nut_dict = {'calories':0,'carbohydrate':0,'protein':0,'fat':0,'weight':0,'errors':''}
        for item in self.recipeingredient_set.all():
            if item.ingredient.nutrition_ingredient_id != None:
                nut_ing = item.ingredient.nutrition_ingredient
                rec_amount = item.amount
                rec_unit = item.unit
                nut_weight = 0
                nut_amount = 1
                for unit_amt in nut_ing.nutritionunit_set.all():
                    if unit_amt.unit == rec_unit:
                        nut_amount = unit_amt.amount
                        nut_weight = unit_amt.weight
                        break
                else:
                    for unit_amt in nut_ing.nutritionunit_set.all():
                        conv_fact = convert(unit_amt.unit,rec_unit)
                        if conv_fact != 0:
                            nut_amount = unit_amt.amount/conv_fact
                            nut_weight = unit_amt.weight
                            break
                    else:
                        nut_dict['errors'] += "No unit-conv: " + item.ingredient.name + " " + rec_unit + " to " + str([n.unit for n in nut_ing.nutritionunit_set.all()]) + "\n"
                tags = nut_dict.keys()
                tags.remove('errors')
                tags.remove('weight')
#                nut_dict['errors'] += str(item) + "\n"
                nut_dict['weight'] += nut_weight*nut_amount
                for tag in tags:
                    nut_calc = int((getattr(nut_ing,tag)*rec_amount*nut_weight*nut_amount)/100)
                    nut_dict[tag] += nut_calc
#                    nut_dict['errors'] += "-" + str(rec_amount*nut_weight/(100*nut_amount)) + " " + tag[:4] + ":" + str(nut_calc)
#                nut_dict['errors'] += "\n"

        tags = nut_dict.keys()
        tags.remove('errors')
        for key in tags:
            nut_dict[key] /= self.servings
        nut_dict['weight'] = int(nut_dict['weight'])
        return nut_dict
            

    def first_letter(self):
        return self.name[0]

    def  __unicode__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("recipe_json_detail",args=[self.slug])

class Ingredient(models.Model):
    name = models.CharField(max_length=100, unique=True)
    grocery_department = models.CharField(max_length=6, choices=DEPT_CHOICES, blank=True)
    nutrition_ingredient = models.ForeignKey('NutritionIngredient',blank=True)

    def __unicode__(self):
        return self.name

    class Meta:
        ordering = ['name']

class FoodPicture(models.Model):
    recipe = models.ForeignKey(Recipe)
    img_address = models.URLField(verbose_name="Image URL (required)", 
                                  help_text="Usually ends in <code>.jpg</code>.")
    link_address = models.URLField(verbose_name="Link (optional)", 
                                   blank = True,
                                   help_text="Main image page.")
    caption = models.TextField(blank=True,
                               verbose_name="Caption (optional)")

class FoodPictureForm(ModelForm):
    class Meta:
        model = FoodPicture
        exclude = ('recipe',)
        widgets = {
            'caption': Textarea(attrs = {'cols':50, 'rows':5})
            }

class RecipeIngredient(models.Model):
    ingredient = models.ForeignKey(Ingredient)
    recipe = models.ForeignKey(Recipe)
    amount = models.DecimalField(max_digits=6, decimal_places=4)
    unit = models.CharField(max_length = 4, choices=UNIT_CHOICES)

    def format_amount(self):
        retval = ''
        intPart = self.amount.quantize(decimal.Decimal('1.'), rounding=decimal.ROUND_DOWN)
        decPart = self.amount % 1
        fracPart = fractions.Fraction.from_decimal(decPart).limit_denominator(16)
        if intPart:
            retval += str(intPart) + ' '
        if fracPart:
            retval += str(fracPart) + ' '
        if self.get_unit_display() != 'item':
            retval += self.get_unit_display()
            if self.amount > 1:
                retval += 's'
        return retval

    def __unicode__(self):
        if self.get_unit_display() == 'to taste':
            return u'{1} {0}'.format(self.format_amount(), self.ingredient)
        else:
            return u'{0} {1}'.format(self.format_amount(), self.ingredient)

class InstructionStep(models.Model):
    this_step = models.TextField('step')
    recipe = models.ForeignKey(Recipe)

    def __unicode__(self):
        return self.this_step

    class Meta:
        verbose_name = 'instruction'

class NutritionIngredient(models.Model):
    name = models.CharField(max_length=100)
    weight_1 = models.DecimalField(max_digits=9,decimal_places=2,default=0,blank=True)
    weight_1_desc = models.CharField(max_length=120,blank=True)
    weight_2 = models.DecimalField(max_digits=9,decimal_places=2,default=0,blank=True)
    weight_2_desc = models.CharField(max_length=120,blank=True)
    water = models.DecimalField(max_digits=10,decimal_places=2,default=0,blank=True)
    calories = models.IntegerField(default=0,blank=True)
    protein = models.DecimalField(max_digits=10,decimal_places=2,default=0,blank=True)
    fat = models.DecimalField(max_digits=10,decimal_places=2,default=0,blank=True)
    ash = models.DecimalField(max_digits=10,decimal_places=2,default=0,blank=True)
    carbohydrate = models.DecimalField(max_digits=10,decimal_places=2,default=0,blank=True)
    fiber = models.DecimalField(max_digits=10,decimal_places=1,default=0,blank=True)
    sugar = models.DecimalField(max_digits=10,decimal_places=2,default=0,blank=True)
    calcium = models.IntegerField(default=0,blank=True)
    iron = models.DecimalField(max_digits=10,decimal_places=2,default=0,blank=True)
    magnesium = models.IntegerField(default=0,blank=True)
    phosphorus = models.IntegerField(default=0,blank=True)
    potassium = models.IntegerField(default=0,blank=True)
    sodium = models.IntegerField(default=0,blank=True)
    zinc = models.DecimalField(max_digits=10,decimal_places=2,default=0,blank=True)
    copper = models.DecimalField(max_digits=10,decimal_places=3,default=0,blank=True)
    manganese = models.DecimalField(max_digits=10,decimal_places=2,default=0,blank=True)
    selenium = models.DecimalField(max_digits=10,decimal_places=1,default=0,blank=True)
    vitamin_c = models.DecimalField(max_digits=10,decimal_places=1,default=0,blank=True)
    thiamin = models.DecimalField(max_digits=10,decimal_places=3,default=0,blank=True)
    riboflavin = models.DecimalField(max_digits=10,decimal_places=3,default=0,blank=True)
    niacin = models.DecimalField(max_digits=10,decimal_places=3,default=0,blank=True)
    panto_acid = models.DecimalField(max_digits=10,decimal_places=3,default=0,blank=True)
    vitamin_b6 = models.DecimalField(max_digits=10,decimal_places=3,default=0,blank=True)
    folate = models.IntegerField(default=0,blank=True)
    folic_acid = models.IntegerField(default=0,blank=True)
    food_folate = models.IntegerField(default=0,blank=True)
    folate_dfe = models.IntegerField(default=0,blank=True)
    choline = models.DecimalField(max_digits=10,decimal_places=2,default=0,blank=True)
    vitamin_b12 = models.DecimalField(max_digits=10,decimal_places=2,default=0,blank=True)
    vitamin_a_iu = models.IntegerField(default=0,blank=True)
    vitamin_a_rae = models.IntegerField(default=0,blank=True)
    retinol = models.IntegerField(default=0,blank=True)
    alpha_carotene = models.IntegerField(default=0,blank=True)
    beta_carotene = models.IntegerField(default=0,blank=True)
    beta_cryptoxanthin = models.IntegerField(default=0,blank=True)
    lycopene = models.IntegerField(default=0,blank=True)
    lutein_zeazanthin = models.IntegerField(default=0,blank=True)
    vitamin_e = models.DecimalField(max_digits=10,decimal_places=2,default=0,blank=True)
    vitamin_d_mcg = models.DecimalField(max_digits=10,decimal_places=1,default=0,blank=True)
    vitamin_d_iu = models.IntegerField(default=0,blank=True)
    vitamin_k = models.DecimalField(max_digits=10,decimal_places=1,default=0,blank=True)
    saturated_fat = models.DecimalField(max_digits=10,decimal_places=3,default=0,blank=True)
    monounsat_fat = models.DecimalField(max_digits=10,decimal_places=3,default=0,blank=True)
    polyunsat_fat = models.DecimalField(max_digits=10,decimal_places=3,default=0,blank=True)
    cholesterol = models.DecimalField(max_digits=10,decimal_places=3,default=0,blank=True)
    refuse_pct = models.IntegerField(default=0,blank=True)

    def __unicode__(self):
        return self.name

    class Meta:
        ordering=['name']

class NutritionUnit(models.Model):
    ingredient = models.ForeignKey(NutritionIngredient)
    amount = models.PositiveIntegerField()
    unit = models.CharField(max_length = 4, choices=UNIT_CHOICES)
    weight = models.DecimalField(max_digits=9,decimal_places=2)

    def __unicode__(self):
        return str(self.amount) + " " + self.unit + " " + str(self.ingredient)

class UserProfile(models.Model):
    user = models.OneToOneField(User)
    fav_recipes = models.ManyToManyField(Recipe)

    def __unicode__(self):
        return "Profile for " + self.user.username

class UserForm(ModelForm):
    class Meta:
        model = User
        fields = ['first_name','last_name','email']
    

def create_user_profile(sender,instance,created,**kwargs):
    if created:
        UserProfile.objects.create(user=instance)

post_save.connect(create_user_profile,sender=User, dispatch_uid="create_user_profile")
