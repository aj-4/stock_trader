from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import mkdtemp
from datetime import datetime

from helpers import *

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

@app.route("/")
@login_required
def index():
    u_id = (session.get("user_id"))

    sum_data = db.execute("SELECT * FROM users WHERE id = :id", id=u_id)
    trans_data = db.execute("SELECT * FROM trans WHERE user_id = :id", id=u_id)
    port_data = db.execute("SELECT * FROM port WHERE user_id = :id", id=u_id)

    #sum transactions and cash
    cash_total = round(sum_data[0]["cash"], 2)
    port_total = 0
    for i in port_data:
        stock_data = lookup(i["symbol"])
        i["currprice"] = round(stock_data["price"], 2)
        i["gainloss"] = round((((stock_data["price"] * i["shares"]) - i["total"]) / i["total"]) * 100, 2)
        port_total += i["currprice"] * i["shares"]
    total = round(cash_total + port_total, 2)
    total_gain = round((((cash_total + port_total) - 10000) / 10000) * 100, 2)

    return render_template("home.html", total=total, cash_total = cash_total, total_gain = total_gain, stocks=port_data)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":

        u_id = (session.get("user_id"))

        #validate inputs
        if not request.form.get("ticker"):
            return apology("please enter a ticker")
        elif not request.form.get("quantity"):
            return apology("please enter a quantity")
        elif int(request.form.get("quantity")) < 1:
            return apology("please enter a quantity greater than 0")

        # query database for stock
        stock = request.form.get("ticker")
        stock_data = lookup(stock)
        if not stock_data:
            return apology("Invalid stock name")

        #pre-format fields
        stock = stock.upper()
        price = stock_data["price"]
        quantity = int(request.form.get("quantity"))
        total = price * quantity

        # check user funds
        funds = db.execute("SELECT cash FROM users WHERE id = :id", id=u_id)
        funds = funds[0]["cash"]

        if total > funds:
            return apology("insufficient funds")

        dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        #log transaction
        db.execute("INSERT INTO trans (user_id, symbol, shares, price, total, buy_sell, datetime) VALUES (:id, :sym, :sh, :pr, :tot, 'BUY', :dt)", id=u_id, sym=stock, sh=quantity, pr=price, tot=total, dt=dt)

        #update portfolio
        if db.execute("SELECT symbol FROM port WHERE user_id = :id AND symbol = :stock", id=u_id, stock=stock):
            db.execute("UPDATE port SET shares = shares + :sh, last_price = :pr, total = total + :tot WHERE user_id = :id AND symbol = :stock", id=u_id, stock=stock, sh=quantity, pr=price, tot=total)
        else:
            db.execute("INSERT INTO port (user_id, symbol, shares, last_price, total) VALUES (:id, :sym, :sh, :pr, :tot)", id=u_id, sym=stock, sh=quantity, pr=price, tot=total)

        #exe new cash balance
        db.execute("UPDATE users SET cash = :newcash WHERE id = :id", newcash=funds-total, id=u_id)

        # redirect user to index page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    u_id = (session.get("user_id"))

    sum_data = db.execute("SELECT * FROM users WHERE id = :id", id=u_id)
    trans_data = db.execute("SELECT * FROM trans WHERE user_id = :id", id=u_id)
    port_data = db.execute("SELECT * FROM port WHERE user_id = :id", id=u_id)

    #sum transactions and cash
    cash_total = round(sum_data[0]["cash"], 2)
    port_total = 0
    for i in port_data:
        stock_data = lookup(i["symbol"])
        i["currprice"] = round(stock_data["price"], 2)
        i["gainloss"] = round((((stock_data["price"] * i["shares"]) - i["total"]) / i["total"]) * 100, 2)
        port_total += i["currprice"] * i["shares"]
    total = round(cash_total + port_total, 2)
    total_gain = round((((cash_total + port_total) - 10000) / 10000) * 100, 2)

    return render_template("history.html", total=total, cash_total = cash_total, total_gain = total_gain, trans=trans_data)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out."""

    # forget any user_id
    session.clear()

    # redirect user to login form
    return redirect(url_for("login"))

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("quote"):
            return apology("please enter a quote")

        ticker = request.form.get("quote")

        # query database for stock
        stock_data = lookup(ticker)

        if stock_data:
            return render_template("quoted.html", ticker=ticker, name=stock_data["name"], price= stock_data["price"], symbol = stock_data["symbol"])
        else:
            return apology("Invalid stock name")

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user."""
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password") and request.form.get("pwconfirm"):
            return apology("must provide password")

        elif not request.form.get("password") == request.form.get("pwconfirm"):
            return apology("passwords must match")

        # query database for username
        name = request.form.get("username")
        pw = pwd_context.hash(request.form.get("password"))

        if db.execute("SELECT * FROM users WHERE username = :name", name=name):
                return apology("user already exists")
        else:
            db.execute("INSERT INTO users (username, hash) VALUES (:name, :hash)", name=name, hash=pw)

        #login user automatically
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=name)

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock."""
    if request.method == "POST":

        u_id = (session.get("user_id"))

        #validate inputs
        if not request.form.get("ticker"):
            return apology("please enter a ticker")
        elif not request.form.get("quantity"):
            return apology("please enter a quantity")
        elif int(request.form.get("quantity")) < 1:
            return apology("please enter a quantity greater than 0")

        #see if user owns stock
        stock = request.form.get("ticker").upper()
        stock_data = lookup(stock)
        if not stock_data:
            return apology("Invalid stock name")
        elif not db.execute("SELECT * FROM port WHERE user_id = :id AND symbol = :stock", id=u_id, stock=stock):
            return apology("You don't own that stock, unfortunately")

        # query yahoo for stock
        price = stock_data["price"]
        quantity = int(request.form.get("quantity"))
        total = price * quantity

        # check quantity owned
        q_owned = db.execute("SELECT shares FROM port WHERE user_id = :id AND symbol = :stock", id=u_id, stock=stock)
        q_owned = q_owned[0]["shares"]
        print(q_owned)

        if q_owned < quantity:
            return apology("insufficient quantity owned")

        dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        #log transaction
        db.execute("INSERT INTO trans (user_id, symbol, shares, price, total, buy_sell, datetime) VALUES (:id, :sym, :sh, :pr, :tot, 'SELL', :dt)", id=u_id, sym=stock, sh=quantity, pr=price, tot=total, dt=dt)

        #update port, if q=0, remove entry
        db.execute("UPDATE port SET shares = shares - :sh, last_price = :pr, total = total - :tot WHERE user_id = :id AND symbol = :stock", id=u_id, stock=stock, sh=quantity, pr=price, tot=total)

        # check quantity owned
        q_owned = db.execute("SELECT shares FROM port WHERE user_id = :id AND symbol = :stock", stock=stock, id=u_id)
        q_owned = q_owned[0]["shares"]

        if q_owned == 0:
            db.execute("DELETE FROM port WHERE user_id=:id AND symbol=:stock", stock=stock, id=u_id)

        #exe new cash balance
        db.execute("UPDATE users SET cash = cash + :newcash WHERE id = :id", newcash=total, id=u_id)

        # redirect user to buy page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("sell.html")

@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    """Reset Password"""
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        if not db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username")):
            return apology("username does not exist, create new account instead")

        # ensure password was submitted
        elif not request.form.get("password") and request.form.get("pwconfirm"):
            return apology("must provide new password")

        elif not request.form.get("password") == request.form.get("pwconfirm"):
            return apology("passwords must match")

        # query database for username
        name = request.form.get("username")
        pw = pwd_context.hash(request.form.get("password"))

        #set new PW
        db.execute("UPDATE users SET hash = :newhash WHERE username = :name", name=name, newhash=pw)

        #login user automatically
        rows = db.execute("SELECT * FROM users WHERE username = :name", name=name)

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("login"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("forgot.html")