
from flask import Flask, render_template, redirect, url_for, request
import mysql.connector
import os
from dotenv import load_dotenv

app = Flask(__name__)

# Load environment variables from .env
load_dotenv()


def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "online_shopping")
    )


# HOME PAGE
@app.route('/')
def home():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute("SELECT * FROM Product ORDER BY ProductID")
    products = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template("index.html", products=products)


# ADD TO CART
@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    db = get_db_connection()
    cursor = db.cursor(buffered=True)

    customer_id = 1

    cursor.execute(
        "SELECT Stock FROM Product WHERE ProductID = %s",
        (product_id,)
    )
    product = cursor.fetchone()

    if product is None or product[0] <= 0:
        cursor.close()
        db.close()
        return redirect(url_for('home'))

    stock = product[0]

    cursor.execute(
        "SELECT CartID FROM Cart WHERE CustomerID = %s",
        (customer_id,)
    )
    cart = cursor.fetchone()

    if cart:
        cart_id = cart[0]
    else:
        cursor.execute(
            "INSERT INTO Cart (CustomerID) VALUES (%s)",
            (customer_id,)
        )
        cart_id = cursor.lastrowid

    cursor.execute(
        """SELECT CartItemID, Quantity
           FROM Cart_Item
           WHERE CartID = %s AND ProductID = %s""",
        (cart_id, product_id)
    )
    item = cursor.fetchone()

    if item:
        if item[1] < stock:
            cursor.execute(
                """UPDATE Cart_Item
                   SET Quantity = Quantity + 1
                   WHERE CartItemID = %s""",
                (item[0],)
            )
    else:
        cursor.execute(
            """INSERT INTO Cart_Item
               (CartID, ProductID, Quantity)
               VALUES (%s, %s, 1)""",
            (cart_id, product_id)
        )

    db.commit()
    cursor.close()
    db.close()

    return redirect(url_for('view_cart'))


# VIEW CART
@app.route('/cart')
def view_cart():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute("""
        SELECT
            ci.CartItemID,
            p.ProductID,
            p.ProductName,
            p.Price,
            p.ImageURL,
            p.Stock,
            ci.Quantity,
            (p.Price * ci.Quantity) AS Total
        FROM Cart_Item ci
        JOIN Product p ON ci.ProductID = p.ProductID
        JOIN Cart c ON ci.CartID = c.CartID
        WHERE c.CustomerID = 1
    """)

    cart_items = cursor.fetchall()

    cursor.close()
    db.close()

    grand_total = sum(float(item['Total']) for item in cart_items)

    return render_template(
        "cart.html",
        cart_items=cart_items,
        grand_total=grand_total
    )


# INCREASE QUANTITY
@app.route('/increase/<int:cart_item_id>', methods=['POST'])
def increase_quantity(cart_item_id):
    db = get_db_connection()
    cursor = db.cursor(buffered=True)

    cursor.execute("""
        SELECT ci.Quantity, p.Stock
        FROM Cart_Item ci
        JOIN Cart c ON ci.CartID = c.CartID
        JOIN Product p ON ci.ProductID = p.ProductID
        WHERE ci.CartItemID = %s AND c.CustomerID = 1
    """, (cart_item_id,))

    item = cursor.fetchone()

    if item and item[0] < item[1]:
        cursor.execute("""
            UPDATE Cart_Item
            SET Quantity = Quantity + 1
            WHERE CartItemID = %s
        """, (cart_item_id,))

    db.commit()
    cursor.close()
    db.close()

    return redirect(url_for('view_cart'))


# DECREASE QUANTITY
@app.route('/decrease/<int:cart_item_id>', methods=['POST'])
def decrease_quantity(cart_item_id):
    db = get_db_connection()
    cursor = db.cursor(buffered=True)

    cursor.execute("""
        SELECT ci.Quantity
        FROM Cart_Item ci
        JOIN Cart c ON ci.CartID = c.CartID
        WHERE ci.CartItemID = %s AND c.CustomerID = 1
    """, (cart_item_id,))

    item = cursor.fetchone()

    if item:
        if item[0] > 1:
            cursor.execute("""
                UPDATE Cart_Item
                SET Quantity = Quantity - 1
                WHERE CartItemID = %s
            """, (cart_item_id,))
        else:
            cursor.execute("""
                DELETE FROM Cart_Item
                WHERE CartItemID = %s
            """, (cart_item_id,))

    db.commit()
    cursor.close()
    db.close()

    return redirect(url_for('view_cart'))


# REMOVE PRODUCT
@app.route('/remove/<int:cart_item_id>', methods=['POST'])
def remove_item(cart_item_id):
    db = get_db_connection()
    cursor = db.cursor(buffered=True)

    cursor.execute("""
        DELETE ci
        FROM Cart_Item ci
        JOIN Cart c ON ci.CartID = c.CartID
        WHERE ci.CartItemID = %s AND c.CustomerID = 1
    """, (cart_item_id,))

    db.commit()
    cursor.close()
    db.close()

    return redirect(url_for('view_cart'))


# CHECKOUT PAGE
@app.route('/checkout')
def checkout():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute("""
        SELECT * FROM Customer
        WHERE CustomerID = 1
    """)
    customer = cursor.fetchone()

    cursor.execute("""
        SELECT
            p.ProductName,
            p.Price,
            ci.Quantity,
            (p.Price * ci.Quantity) AS Total
        FROM Cart_Item ci
        JOIN Product p ON ci.ProductID = p.ProductID
        JOIN Cart c ON ci.CartID = c.CartID
        WHERE c.CustomerID = 1
    """)

    cart_items = cursor.fetchall()

    cursor.close()
    db.close()

    if not customer or not cart_items:
        return redirect(url_for('view_cart'))

    grand_total = sum(float(item['Total']) for item in cart_items)

    return render_template(
        "checkout.html",
        customer=customer,
        cart_items=cart_items,
        grand_total=grand_total
    )


# PLACE ORDER
@app.route('/place_order', methods=['POST'])
def place_order():
    db = get_db_connection()
    cursor = db.cursor(buffered=True)

    customer_id = 1

    try:
        cursor.execute("""
            SELECT
                ci.ProductID,
                ci.Quantity,
                p.Price,
                p.Stock
            FROM Cart_Item ci
            JOIN Cart c ON ci.CartID = c.CartID
            JOIN Product p ON ci.ProductID = p.ProductID
            WHERE c.CustomerID = %s
        """, (customer_id,))

        items = cursor.fetchall()

        if not items:
            db.rollback()
            return redirect(url_for('view_cart'))

        grand_total = 0

        for item in items:
            product_id, quantity, price, stock = item

            if quantity > stock:
                db.rollback()
                return "Insufficient stock for a product. Please return to cart."

            grand_total += float(price) * quantity

        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']

        cursor.execute("""
            UPDATE Customer
            SET Name = %s,
                Email = %s,
                Phone = %s,
                Address = %s
            WHERE CustomerID = %s
        """, (name, email, phone, address, customer_id))

        cursor.execute("""
            INSERT INTO Orders
            (CustomerID, OrderDate, TotalAmount)
            VALUES (%s, CURDATE(), %s)
        """, (customer_id, grand_total))

        order_id = cursor.lastrowid

        for item in items:
            product_id, quantity, price, stock = item

            cursor.execute("""
                INSERT INTO Order_Item
                (OrderID, ProductID, Quantity)
                VALUES (%s, %s, %s)
            """, (order_id, product_id, quantity))

            cursor.execute("""
                UPDATE Product
                SET Stock = Stock - %s
                WHERE ProductID = %s
            """, (quantity, product_id))

        cursor.execute("""
            INSERT INTO Payment
            (OrderID, PaymentDate, Amount, PaymentStatus)
            VALUES (%s, CURDATE(), %s, 'Pending')
        """, (order_id, grand_total))

        cursor.execute("""
            DELETE ci
            FROM Cart_Item ci
            JOIN Cart c ON ci.CartID = c.CartID
            WHERE c.CustomerID = %s
        """, (customer_id,))

        db.commit()

        return render_template(
            "success.html",
            order_id=order_id,
            grand_total=grand_total
        )

    except Exception as e:
        db.rollback()
        return "Order could not be placed. Error: " + str(e)

    finally:
        cursor.close()
        db.close()


if __name__ == '__main__':
    app.run(debug=True)
