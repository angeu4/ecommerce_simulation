def test_full_user_flow(client):
    # 1) Create user
    res = client.post("/users", json={
        "username": "alice",
        "password": "secret"
    })
    assert res.status_code == 201

    # 2) Login
    res = client.post("/auth/user/login", json={
        "username": "alice",
        "password": "secret"
    })
    assert res.status_code == 200
    token = res.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}

    # 3) Add cart items
    res = client.post("/cart/items", json={
        "items": [
            {"sku": "SKU-1", "name": "Banana", "qty": 2, "price": 3.5},
            {"sku": "SKU-2", "name": "Orange", "qty": 1, "price": 2.0},
        ]
    }, headers=headers)
    assert res.status_code == 201

    # 4) Checkout
    res = client.post("/checkout", json={"discount_code": None}, headers=headers)
    assert res.status_code == 201
    data = res.json()

    assert data["subtotal"] == 9.0
    assert data["discount"] == 0
    assert data["total"] == 9.0

    # 5) Logout
    res = client.post("/auth/user/logout", headers=headers)
    assert res.status_code == 200
