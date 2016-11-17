"""What's up Doc"""

import os
import module
from random import randint
from jinja2 import StrictUndefined

from flask import jsonify
from flask import (Flask, render_template, redirect, request, flash,
                   session)
from flask_mail import Mail, Message

from flask_debugtoolbar import DebugToolbarExtension
import requests
import json
from model import connect_to_db, db, User, Doctor, Like

# ***************************** To use Yelp API:
from yelp.client import Client 
import io

# ***************************** To hash password:
from passlib.hash import pbkdf2_sha256

# Trying Google static for email:
from cStringIO import StringIO
from PIL import Image
import urllib


app = Flask(__name__)

# Required to use Flask sessions and the debug toolbar
app.secret_key = "ABC" 
# ***************************** Flask mail settings:

email_password = os.environ['EMAIL_PASSWORD']
app.config['MAIL_SERVER']='smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_DEFAULT_SENDER'] = 'whatsup.doctor.website@gmail.com'
app.config['MAIL_USERNAME'] = 'whatsup.doctor.website@gmail.com'
app.config['MAIL_PASSWORD'] = email_password
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True

mail = Mail(app)




# Normally, if you use an undefined variable in Jinja2, it fails
# silently. This is horrible. Fix this so that, instead, it raises an
# error.

app.jinja_env.undefined = StrictUndefined
app.jinja_env.auto_reload = True


# Government API /extract from secret.sh
secret_token = os.environ["DOC_APP_TOKEN"]

google_key = os.environ["GOOGLE_KEY"]

# Yelp API
client_id = os.environ["YELP_APP_ID"]
client_secret = os.environ["YELP_APP_SECRET"]
url_yelp='https://api.yelp.com/oauth2/token'
data_yelp ={'grand_type': 'client_credentials',
    'client_id': client_id, 'client_secret': client_secret}
r = requests.post(url_yelp, data = data_yelp)

yelp_access_token = r.json()['access_token']
yelp_search_url = 'https://api.yelp.com/v3/businesses/search'
headers = {'Authorization': 'Bearer ' + yelp_access_token}

@app.route('/')
def index():
    """Homepage."""

    # p_id = 49877

    # # parameter including app_secret
    # payload = {'$$app_token': secret_token,
    #             'physician_profile_id': p_id}

    # response = requests.get("https://openpaymentsdata.cms.gov/resource/tf25-5jad.json", params=payload)
    
    # # response = "https://openpaymentsdata.cms.gov/resource/tf25-5jad.json?$$app_token=secret_token&physician_profile_id=49877"
    # response = response.json()
    
    return render_template('homepage.html')

@app.route("/results_list")
def results_list():
    """Show list of doctor resulting from search."""
    firstname = request.args.get('firstname')
    lastname = request.args.get('lastname')
    data = {'$$app_token': secret_token,
                'physician_first_name': firstname,
                'physician_last_name': lastname}
    
    response = requests.get("https://openpaymentsdata.cms.gov/resource/tf25-5jad.json", params=data)
    # Try to use several keys to see if it return something different than empty list:
    trial = 0
    key_list = [secret_token, os.environ["DOC_APP_TOKEN1"], os.environ['DOC_APP_TOKEN2']]
    while trial < 50:
        response = requests.get("https://openpaymentsdata.cms.gov/resource/tf25-5jad.json", params=data)
        search_results = response.json()
        if search_results != []:
            print 'NOT EMPTY'
            break
        else:
            print 'EMPTY'
            t = randint(0,2)
            data['$$app_token'] = key_list[t]
            response = requests.get("https://openpaymentsdata.cms.gov/resource/tf25-5jad.json", params=data)
            trial = trial + 1
            print response.json()
          
    search_results = response.json()
    if search_results == []:
        return render_template('no_result.html')

    # to keep only unique id of doctor so no duplicates in list of results:
    search_results = module.unique_dico(search_results)
    return render_template('results_list.html', search_results=search_results)

@app.route("/doc_summary/<int:physician_profile_id>")
def summary(physician_profile_id):
    """Show summary page on doctor resulting from search."""
    # Govt API Request
    summ = {'$$app_token': secret_token,
                'physician_profile_id': physician_profile_id
            }

    # Issue request to Govt API/ Extract doctor personal info/ Caluclate payments received by doctor
    response = requests.get("https://openpaymentsdata.cms.gov/resource/tf25-5jad.json", params=summ)
    search_results = response.json()
    t = module.total_payments(search_results)
    first_name = search_results[0]['physician_first_name']
    last_name = search_results[0]['physician_last_name']
    info_doc = module.perso_doc_info(search_results)
    pay_breakdown = module.pay_per_comp(search_results)
    # List of tuple ; tuple = (pharmacy name, total):
    top_pharm = module.pay_per_comp_filtered(pay_breakdown,t)
   

    # Setting relevant values in session that I am going to need later:
    
    session['info_doc'] = info_doc
    session['info_doc']['total_received'] = round(t,2)
    session['pay_breakdown'] = top_pharm
    session['doc_chart_pharm'] = module.tuplelist_to_listfirstitem(top_pharm)
    session['doc_chart_payment'] = module.tuplelist_to_listseconditem(top_pharm)
   
  
    top_pharm_dic_no_other = top_pharm
    if len(top_pharm_dic_no_other) > 4:
        top_pharm_dic_no_other.pop()
    session['listsamecompanies'] = module.tuplelist_to_listfirstitem(top_pharm_dic_no_other)
    session['doc_payments_no_other']=module.tuplelist_to_listseconditem(top_pharm_dic_no_other)
    
 
    # Nber of Like for this doctor section:
    nb_likes = 0
    doctor1 = db.session.query(Doctor).filter(Doctor.doctor_id==info_doc['p_id']).first()
    if doctor1:
        nb_likes = Like.query.filter_by(doctor_id=session['info_doc']['p_id']).count()
    session['likes'] = nb_likes
        
    # Check if user did like this doctor
    liked_check = None
    if session.get('user_id'):
        liked_check = db.session.query(Like).filter(Like.doctor_id==info_doc['p_id'], 
            Like.user_id == session['user_id']).first()

  
    
    
    # Yelp API request
    # storer rating in session
    
    params = {
    'term': session['info_doc']['last_name'],
    'location':  session['info_doc']['city'] + session['info_doc']['zipcode'],
    'categories': 'health'

    }

    result = requests.get(url=yelp_search_url, params=params, headers=headers)

    businesses = result.json()['businesses']
    for business in businesses:
        name = business['name'].upper()
        city = business['location']['city'].upper()
        if session['info_doc']['last_name'] in name and session['info_doc']['city'] in city and session['info_doc']['first_name'] in name:
            session['info_doc']['rating'] = business['rating']
            session['info_doc']['url'] = business['url']
            
            break
   # Google Map API
    title_address = "%s %s %s %s "%(session['info_doc']['street_address'],
        session['info_doc']['zipcode'], session['info_doc']['city'],
                session['info_doc']['state'])
    payloadG = {'key': google_key,
                'address': title_address }
    response_google = requests.get("https://maps.googleapis.com/maps/api/geocode/json", params=payloadG)
    
    response_google = response_google.json()
    lat = response_google['results'][0]['geometry']['location']['lat']
    lng = response_google['results'][0]['geometry']['location']['lng']

    # Test for sending email set up:
    session['info_doc']['lat'] = lat
    session['info_doc']['lng'] = lng 
    session['info_doc']['gmap_address'] = title_address

   # Return parameters to jinja  
    return render_template("summary.html", liked_check=liked_check,
        google_key=google_key, lat=lat, lng=lng, title_address=title_address)

 
@app.route("/ind_comparison/<int:physician_profile_id>/<specialty>/<state>/<city>")
def ind_comparison(physician_profile_id, specialty, state, city):
    """Show payments received by doctor in comparison to payments received by 
    all doctors of the same specialty"""
    
    summ = {'$$app_token': secret_token,
            'physician_specialty': specialty,
            'recipient_state': state
            }

    response = requests.get("https://openpaymentsdata.cms.gov/resource/tf25-5jad.json", params=summ, stream=True)
    all_payments = module.results_per_spe(response)
    # avg_per_state: Average payments recived by all doctors of the specialty in this state:
    avg_per_state = round(module.averg_per_state(all_payments),2)
    #avg_pharm: dictionnary with key: pharmacy, value: avg payed doc for specific specialty & state:
    avg_pharm = module.averg_per_company(all_payments) 
    # session['pay_breakdown'] : list of tuple with (pharmacy name, total payment)
    avg_pharm_match_doc = module.averg_ind_comp_doc(avg_pharm, session['pay_breakdown'])
    session['doc_comp'] = module.list_tup_to_dic(session['pay_breakdown'])
    session['pharm_avg'] = module.pharm_avg_sortedlist(avg_pharm_match_doc)
    
    # Extract doctors of same city and specialty:
    same_city = {'$$app_token': secret_token,
            'physician_specialty': specialty,
            'recipient_city': city
            }
    record_same_city = requests.get("https://openpaymentsdata.cms.gov/resource/tf25-5jad.json", params=same_city, stream=True)
    

    # three better doctors
    all_doc = module.three_better_doc(record_same_city, session['info_doc']['p_id'])
    # Make sure no error if all_doc have elss than 10 or no elements:
    if len(all_doc) <10:
        selected_list = all_doc.items()[:len(all_doc)]
    elif len(all_doc) == 0:
        selected_list = []
    else:
        selected_list = all_doc.items()[:10]
        print selected_list
    selected_doc = {}

    # Extract for each doctor its total received
    for elem in selected_list:
        data1 = {'$$app_token': secret_token,
                'physician_profile_id': elem[0]}
        response1 = requests.get("https://openpaymentsdata.cms.gov/resource/tf25-5jad.json", params=data1)
        selected_doc[elem[0]] = module.total_payments(response1.json())
    # Compared each doctor total received to doctor entered in search and keep it if below
    best_doc = module.best_ten_doc(selected_doc, session['info_doc']['total_received'])
    best_doc = module.best_doc_sorted(best_doc)

    
    return render_template('ind_comparison.html', avg_per_state=avg_per_state, 
        avg_pharm=avg_pharm, avg_pharm_ind_doc=avg_pharm_match_doc, best_doc=best_doc, 
        len = len(best_doc))


@app.route('/doc_info.json')
def payment_doc():
    """Return data about payments received by doctor per each company."""

# Be careful here , formatted for only 5 companies
    data_dict = {
                "labels":  session['doc_chart_pharm'],
                "datasets": [
                    {
                        "data": session['doc_chart_payment'],
                        "backgroundColor": [
                            "#FF6384",
                            "#36A2EB",
                            "#FFCE56",
                            "#02c8a7",
                            "#552847"
                        ],
                        "hoverBackgroundColor": [
                            "#FF6384",
                            "#36A2EB",
                            "#FFCE56",
                            "#02c8a7",
                            "#552847"
                        ]
                
                    }]
            }

    return jsonify(data_dict)

            
@app.route("/ind_info.json")
def payment_ind_doc():
    """Return data about average payments made by each company to same specialty of doc 
    versus payment receievd by specific doctor of same specialty."""
    print '--------------- Chart bar DATA --------------------'
    print session['listsamecompanies']
    print session['pharm_avg']
    data_dict = {
                "labels": session['listsamecompanies'],
                "datasets":[
                    {
                        "label": "Payments Received by this specific Doctor",
                        "data": session['doc_payments_no_other'],
                        "borderColor": '#00FF00',
                        "borderWidth": 2,
                        "stack": 1,
                        "backgroundColor": "rgba(99,255,132,0.2)"
                        
                
                    },
                    {
                        "label": "Average Payments spent on this Specialty per Doctor",
                        "data": session['pharm_avg'],
                        "borderColor": '#00FF00',
                        "borderWidth": 2,
                        "stack": 2,
                        "backgroundColor": "rgba(255,99,132,0.2)"
                        
                
                    }]
                }
    return jsonify(data_dict)

@app.route("/sign_in")
def sign_in():
    """Sign-in access."""

    return render_template("sign_in.html")

@app.route('/confirmation-sign_in', methods=["POST"])
def conf_sign_in():
    """Conf sign-in"""
    fname = request.form.get('fname')
    lname = request.form.get('lname')
    email = request.form.get('email')
    password = request.form.get('password')
    hash = pbkdf2_sha256.encrypt(password, rounds=200000, salt_size=16)
    
    age = request.form.get('age')
    zipcode = request.form.get('zipcode')
    q1 = User.query.filter_by(email=email).first()
    if q1 == None:
        if age:
            u1 = User(first_name = fname, last_name= lname, email=email, password=hash,
            age = int(age), zipcode = int(zipcode))
        else:
            u1 = User(first_name = fname, last_name= lname, email=email, password=password,
             zipcode = int(zipcode))
        db.session.add(u1)
        db.session.commit()
        return render_template('conf_sign_in.html', email=email, passw=password)
    else:
        flash("It is already taken, please choose smthg else")
        return redirect('/sign_in')

@app.route("/log_in")
def log_in():
    """Log-in."""
    if session.get('user_id'):
        flash("You are already logged in.")
        return redirect('/user_page')
    return render_template("log_in.html")

@app.route('/logged', methods=['POST'])
def logged():
    email = request.form.get('email')
    password = request.form.get('password')
    user = db.session.query(User).filter(User.email==email).first()
    user_id = user.user_id
    if user == None:
        flash("No such user")
        return redirect('/log_in')
    else:
        
        if pbkdf2_sha256.verify(password, user.password):
        # if user.password == password:
            flash("Welcome to What's up Doc")
            session["user_id"]= user_id
            return redirect('/user_page')
        else:
            flash("Wrong password, please try again.")
            return redirect('/log_in')

# check why email bug when i log out when im already logged out
@app.route("/log_out")
def log_out():
    """Log user out."""

    if session.get('user_id',0) == 0:
        flash("You are not logged in.")
        return redirect("/")
    else:
        del session["user_id"]
        flash("Logged out.")
    return redirect("/")


# Like button
@app.route('/like', methods=["POST"])
def like():
    # doctor0 = db.session.query(Doctor).filter(Doctor.doctor_id==session['info_doc']['p_id']).first()
    doctor0 = Doctor.query.get(session['info_doc']['p_id'])
    if doctor0 is None:
        doctor1 = Doctor(doctor_id = session['info_doc']['p_id'],first_name = 
        session['info_doc']['first_name'],last_name=session['info_doc']['last_name'],
        specialty= session['info_doc']['short_specialty'],yelp_rating = session['info_doc']['rating'])
        db.session.add(doctor1)
    like1 = Like(doctor_id=session['info_doc']['p_id'], user_id=session['user_id'])
    db.session.add(like1)
    db.session.commit()
    nb_likes = Like.query.filter_by(doctor_id=session['info_doc']['p_id']).count()
    session['likes'] = nb_likes
    return jsonify({'like': nb_likes})

@app.route('/unlike', methods=["POST"])
def unlike():
    
    Like.query.filter_by(doctor_id=session['info_doc']['p_id'], user_id=session['user_id']).delete()
    db.session.commit()
    nb_likes = Like.query.filter_by(doctor_id=session['info_doc']['p_id']).count()
    session['likes'] = nb_likes
    return jsonify({'unlike': nb_likes})


@app.route("/user_page")
def user_page():
    """User_page."""
    user1 = db.session.query(User).filter(User.user_id==session['user_id']).first()
    fname = user1.first_name
    lname = user1.last_name
    email = user1.email
    zipcode = user1.zipcode

    likes = db.session.query(Like).filter(Like.user_id==session['user_id']).all()
    nb_vote = db.session.query(Like).filter(Like.user_id==session['user_id']).count()
   
    return render_template("user.html", fname = fname, lname=lname, email=email, 
        zipcode=zipcode, likes=likes ,nb_vote=nb_vote)

@app.route("/send_email", methods=['POST'])
def send_email():
    recipients = email = request.form.get('emailAddress')
    msg = Message("What's Up Doc informs you!", recipients=[recipients])
    msg.body = "testing"

    # Getting the Google Image:
    # payloadG = {'key': google_key,
    #             'address': title_address }
    url = "http://maps.googleapis.com/maps/api/staticmap?center=%s,%s&size=800x800&zoom=14&sensor=false"%(session['info_doc']['lat'],session['info_doc']['lng'])
    print url
    buffer = StringIO(urllib.urlopen(url).read())
    image1 = Image.open(buffer)
    image1.save("static/img/map.png")
    print image1
    # image = image.show()

    msg.html = render_template('summary_to_send.html', lat=session['info_doc']['lat'],
    lng=session['info_doc']['lng'], title_address =session['info_doc']['gmap_address'],
    google_key=google_key)
    with app.open_resource("static/img/map.png") as fp:
        msg.attach("static/img/map.png", "image/png", fp.read())
    mail.send(msg)
    return jsonify({'status':'Sent'})


if __name__ == "__main__":
    # We have to set debug=True here, since it has to be True at the
    # point that we invoke the DebugToolbarExtension
    app.debug = True

    connect_to_db(app)

    # Use the DebugToolbar
    DebugToolbarExtension(app)


    
    app.run(port=5000, host="0.0.0.0")
