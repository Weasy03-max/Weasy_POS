import os, csv, io, secrets
from datetime import datetime, date, timedelta
from functools import wraps
from decimal import Decimal, InvalidOperation
from flask import Flask, render_template, redirect, url_for, flash, request, make_response, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm, CSRFProtect
from wtforms import StringField, PasswordField, SubmitField, DecimalField, IntegerField, SelectField
from wtforms.validators import DataRequired, Length, NumberRange, Optional
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-me-" + secrets.token_hex(16))
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///weasy_pos.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("COOKIE_SECURE", "0") == "1"
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
csrf = CSRFProtect(app)
CURRENCY = os.getenv("CURRENCY", "ZMW")

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="cashier")
    active = db.Column(db.Boolean, default=True)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    sku = db.Column(db.String(60), unique=True, nullable=False)
    barcode = db.Column(db.String(100), unique=True)
    category = db.Column(db.String(80), default="General")
    price = db.Column(db.Numeric(12,2), nullable=False)
    cost = db.Column(db.Numeric(12,2), default=0)
    stock = db.Column(db.Integer, nullable=False, default=0)
    low_stock = db.Column(db.Integer, default=5)
    active = db.Column(db.Boolean, default=True)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    phone = db.Column(db.String(40))
    email = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    receipt_no = db.Column(db.String(40), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    subtotal = db.Column(db.Numeric(12,2), nullable=False)
    discount = db.Column(db.Numeric(12,2), default=0)
    total = db.Column(db.Numeric(12,2), nullable=False)
    payment_method = db.Column(db.String(30), nullable=False)
    amount_paid = db.Column(db.Numeric(12,2), nullable=False)
    change_due = db.Column(db.Numeric(12,2), default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship("Customer")
    cashier = db.relationship("User")

class SaleItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sale.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    product_name = db.Column(db.String(140), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(12,2), nullable=False)
    line_total = db.Column(db.Numeric(12,2), nullable=False)
    product = db.relationship("Product")

class StockMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    quantity_change = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ProductForm(FlaskForm):
    name=StringField("Product name", validators=[DataRequired(),Length(max=140)])
    sku=StringField("SKU", validators=[DataRequired(),Length(max=60)])
    barcode=StringField("Barcode", validators=[Optional(),Length(max=100)])
    category=StringField("Category", validators=[Optional(),Length(max=80)])
    price=DecimalField("Selling price", places=2, validators=[DataRequired(),NumberRange(min=0)])
    cost=DecimalField("Cost price", places=2, validators=[Optional(),NumberRange(min=0)])
    stock=IntegerField("Opening stock", validators=[DataRequired(),NumberRange(min=0)])
    low_stock=IntegerField("Low-stock alert at", validators=[DataRequired(),NumberRange(min=0)])
    submit=SubmitField("Save product")

class LoginForm(FlaskForm):
    username=StringField("Username", validators=[DataRequired()])
    password=PasswordField("Password", validators=[DataRequired()])
    submit=SubmitField("Sign in")

class CustomerForm(FlaskForm):
    name=StringField("Full name", validators=[DataRequired(),Length(max=140)])
    phone=StringField("Phone", validators=[Optional(),Length(max=40)])
    email=StringField("Email", validators=[Optional(),Length(max=120)])
    submit=SubmitField("Save customer")

@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))

def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin":
            flash("Administrator permission required.", "danger")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)
    return wrapped

@app.context_processor
def inject_globals(): return {"currency": CURRENCY, "now": datetime.utcnow}

@app.route("/")
@login_required
def dashboard():
    today=date.today()
    sales_today=Sale.query.filter(func.date(Sale.created_at)==today.isoformat()).all()
    total_today=sum((s.total for s in sales_today), Decimal("0.00"))
    low=Product.query.filter(Product.active.is_(True), Product.stock <= Product.low_stock).order_by(Product.stock).limit(8).all()
    recent=Sale.query.order_by(Sale.created_at.desc()).limit(8).all()
    return render_template("dashboard.html", total_today=total_today, count_today=len(sales_today),
        product_count=Product.query.filter_by(active=True).count(), customer_count=Customer.query.count(),
        low=low, recent=recent)

@app.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated: return redirect(url_for("dashboard"))
    form=LoginForm()
    if form.validate_on_submit():
        user=User.query.filter_by(username=form.username.data.strip(), active=True).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Incorrect username or password.", "danger")
    return render_template("login.html", form=form)

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/products")
@login_required
def products():
    q=request.args.get("q","").strip()
    query=Product.query.filter_by(active=True)
    if q: query=query.filter(db.or_(Product.name.ilike(f"%{q}%"),Product.sku.ilike(f"%{q}%"),Product.barcode.ilike(f"%{q}%")))
    return render_template("products.html", products=query.order_by(Product.name).all(), q=q)

@app.route("/products/new", methods=["GET","POST"])
@admin_required
def product_new():
    form=ProductForm()
    if form.validate_on_submit():
        p=Product(name=form.name.data.strip(),sku=form.sku.data.strip(),barcode=form.barcode.data.strip() or None,
          category=form.category.data.strip() or "General",price=form.price.data,cost=form.cost.data or 0,
          stock=form.stock.data,low_stock=form.low_stock.data)
        db.session.add(p); db.session.flush()
        if p.stock: db.session.add(StockMovement(product_id=p.id,user_id=current_user.id,quantity_change=p.stock,reason="Opening stock"))
        try: db.session.commit(); flash("Product saved.", "success"); return redirect(url_for("products"))
        except Exception: db.session.rollback(); flash("SKU or barcode already exists.", "danger")
    return render_template("product_form.html",form=form,title="Add product")

@app.route("/products/<int:pid>/edit", methods=["GET","POST"])
@admin_required
def product_edit(pid):
    p=Product.query.get_or_404(pid); form=ProductForm(obj=p)
    if request.method=="GET": form.stock.data=p.stock
    if form.validate_on_submit():
        delta=form.stock.data-p.stock
        for field in ["name","sku","barcode","category","price","cost","low_stock"]: setattr(p,field,getattr(form,field).data)
        p.barcode=p.barcode or None
        if delta: db.session.add(StockMovement(product_id=p.id,user_id=current_user.id,quantity_change=delta,reason="Stock adjustment"))
        p.stock=form.stock.data
        try: db.session.commit(); flash("Product updated.", "success"); return redirect(url_for("products"))
        except Exception: db.session.rollback(); flash("SKU or barcode already exists.", "danger")
    return render_template("product_form.html",form=form,title="Edit product")

@app.route("/customers", methods=["GET","POST"])
@login_required
def customers():
    form=CustomerForm()
    if form.validate_on_submit():
        db.session.add(Customer(name=form.name.data.strip(),phone=form.phone.data,email=form.email.data))
        db.session.commit(); flash("Customer saved.", "success"); return redirect(url_for("customers"))
    q=request.args.get("q","").strip()
    query=Customer.query
    if q: query=query.filter(db.or_(Customer.name.ilike(f"%{q}%"),Customer.phone.ilike(f"%{q}%")))
    return render_template("customers.html",form=form,customers=query.order_by(Customer.name).all(),q=q)

@app.route("/pos")
@login_required
def pos():
    products=Product.query.filter(Product.active.is_(True),Product.stock>0).order_by(Product.name).all()
    customers=Customer.query.order_by(Customer.name).all()
    return render_template("pos.html",products=products,customers=customers)

@app.route("/checkout", methods=["POST"])
@login_required
def checkout():
    try:
        import json
        cart=json.loads(request.form.get("cart","[]"))
        if not isinstance(cart,list) or not cart: raise ValueError("Cart is empty.")
        customer_id=request.form.get("customer_id") or None
        customer=db.session.get(Customer,int(customer_id)) if customer_id else None
        method=request.form.get("payment_method","Cash")
        if method not in ["Cash","Mobile Money","Card","Bank Transfer"]: raise ValueError("Invalid payment method.")
        discount=Decimal(request.form.get("discount","0"))
        if discount < 0: raise ValueError("Invalid discount.")
        lines=[]; subtotal=Decimal("0.00")
        for item in cart:
            pid=int(item["id"]); qty=int(item["qty"])
            if qty < 1: raise ValueError("Invalid quantity.")
            p=Product.query.filter_by(id=pid,active=True).with_for_update().first()
            if not p or p.stock < qty: raise ValueError("Insufficient stock for one or more products.")
            line=(Decimal(p.price)*qty).quantize(Decimal("0.01"))
            lines.append((p,qty,line)); subtotal+=line
        if discount > subtotal: raise ValueError("Discount cannot exceed subtotal.")
        total=(subtotal-discount).quantize(Decimal("0.01"))
        paid=Decimal(request.form.get("amount_paid","0"))
        if paid < total: raise ValueError("Amount paid is less than total.")
        sale=Sale(receipt_no="WPS-"+datetime.utcnow().strftime("%Y%m%d%H%M%S")+"-"+secrets.token_hex(2).upper(),
          customer_id=customer.id if customer else None,user_id=current_user.id,subtotal=subtotal,discount=discount,total=total,
          payment_method=method,amount_paid=paid,change_due=paid-total)
        db.session.add(sale); db.session.flush()
        for p,qty,line in lines:
            p.stock-=qty
            db.session.add(SaleItem(sale_id=sale.id,product_id=p.id,product_name=p.name,quantity=qty,unit_price=p.price,line_total=line))
            db.session.add(StockMovement(product_id=p.id,user_id=current_user.id,quantity_change=-qty,reason=f"Sale {sale.receipt_no}"))
        db.session.commit()
        return redirect(url_for("receipt",sale_id=sale.id))
    except (ValueError, KeyError, TypeError, InvalidOperation) as e:
        db.session.rollback(); flash(str(e), "danger"); return redirect(url_for("pos"))
    except Exception:
        db.session.rollback(); flash("Sale could not be completed. Please check stock and try again.", "danger"); return redirect(url_for("pos"))

@app.route("/sales")
@login_required
def sales():
    start=request.args.get("start"); end=request.args.get("end")
    query=Sale.query
    if start:
        try: query=query.filter(Sale.created_at>=datetime.fromisoformat(start))
        except ValueError: pass
    if end:
        try: query=query.filter(Sale.created_at<datetime.fromisoformat(end)+timedelta(days=1))
        except ValueError: pass
    return render_template("sales.html",sales=query.order_by(Sale.created_at.desc()).limit(300).all(),start=start or "",end=end or "")

@app.route("/receipt/<int:sale_id>")
@login_required
def receipt(sale_id):
    sale=Sale.query.get_or_404(sale_id)
    if current_user.role!="admin" and sale.user_id!=current_user.id: abort(403)
    items=SaleItem.query.filter_by(sale_id=sale.id).all()
    return render_template("receipt.html",sale=sale,items=items)

@app.route("/reports")
@admin_required
def reports():
    today=date.today()
    start=today-timedelta(days=6)
    rows=db.session.query(func.date(Sale.created_at),func.sum(Sale.total),func.count(Sale.id)).filter(Sale.created_at>=start).group_by(func.date(Sale.created_at)).all()
    labels=[(start+timedelta(days=i)).isoformat() for i in range(7)]
    totals={str(r[0]):float(r[1] or 0) for r in rows}
    return render_template("reports.html",labels=labels,values=[totals.get(x,0) for x in labels],
       all_sales=Sale.query.count(),all_products=Product.query.filter_by(active=True).count())

@app.route("/users", methods=["GET","POST"])
@admin_required
def users():
    if request.method=="POST":
        username=request.form.get("username","").strip()
        password=request.form.get("password","")
        role=request.form.get("role","cashier")
        if len(username)<3 or len(password)<10 or role not in ["admin","cashier"]:
            flash("Username must be 3+ characters, password 10+ characters, and role valid.", "danger")
        elif User.query.filter_by(username=username).first():
            flash("Username already exists.", "danger")
        else:
            u=User(username=username,role=role); u.set_password(password); db.session.add(u); db.session.commit()
            flash("User created.", "success")
        return redirect(url_for("users"))
    return render_template("users.html",users=User.query.order_by(User.username).all())

@app.route("/export/sales.csv")
@admin_required
def export_sales():
    output=io.StringIO(); writer=csv.writer(output)
    writer.writerow(["Receipt","Date","Cashier","Customer","Subtotal","Discount","Total","Payment"])
    for s in Sale.query.order_by(Sale.created_at.desc()).all():
        writer.writerow([s.receipt_no,s.created_at.isoformat(),s.cashier.username,s.customer.name if s.customer else "",s.subtotal,s.discount,s.total,s.payment_method])
    response=make_response(output.getvalue())
    response.headers["Content-Disposition"]="attachment; filename=weasy_sales.csv"
    response.headers["Content-Type"]="text/csv"
    return response

@app.errorhandler(403)
def forbidden(e): return render_template("error.html",code=403,message="You do not have permission to access this page."),403
@app.errorhandler(404)
def missing(e): return render_template("error.html",code=404,message="The requested page was not found."),404

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username=os.getenv("ADMIN_USERNAME","admin")).first():
        admin=User(username=os.getenv("ADMIN_USERNAME","admin"),role="admin")
        admin.set_password(os.getenv("ADMIN_PASSWORD","ChangeThisImmediately123!"))
        db.session.add(admin); db.session.commit()

if __name__=="__main__":
    # For local development only. Use gunicorn + HTTPS for public cloud deployment.
    app.run(host=os.getenv("HOST","127.0.0.1"),port=int(os.getenv("PORT","5000")),debug=False)
