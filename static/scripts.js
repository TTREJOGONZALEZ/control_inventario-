
document.addEventListener("DOMContentLoaded", function () {
    const producto = document.getElementById("producto");
    const cantidad = document.getElementById("cantidad");
    const totalVenta = document.getElementById("totalVenta");

    if (!producto || !cantidad || !totalVenta) {
        return;
    }

    function calcularTotal() {
        const opcion = producto.options[producto.selectedIndex];
        const precio = Number(opcion?.dataset.precio || 0);
        const unidades = Number(cantidad.value) || 0;

        const total = precio * Math.max(0, unidades);

        totalVenta.textContent = total.toLocaleString("es-MX", {
            style: "currency",
            currency: "MXN"
        });
    }

    producto.addEventListener("change", calcularTotal);
    cantidad.addEventListener("input", calcularTotal);

    calcularTotal();
});
