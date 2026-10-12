# Configuración de comercio de FitAI Style

La tienda está en modo de pruebas por defecto. No publiques ventas reales hasta completar pruebas de pago, envíos, reembolsos y avisos legales.

## Variables de entorno del backend (Render)

Configúralas en el servicio del backend, nunca en JavaScript del frontend:

- `FRONTEND_URL`: URL pública de la web, por ejemplo `https://fitai-style-frontend.vercel.app`.
- `PAYMENTS_ENV=sandbox`: mantiene Mercado Pago en pruebas. Cambia a `production` solo después de validar las pruebas y usar credenciales de producción.
- `MP_ACCESS_TOKEN`: token del servidor en Mercado Pago Developers.
- `MP_NOTIFICATION_URL`: URL HTTPS del webhook, por ejemplo `https://TU-BACKEND.onrender.com/api/tienda/webhooks/mercadopago`.
- `WOMPI_PUBLIC_KEY`: llave pública del comercio; en pruebas normalmente comienza por `pub_test_`.
- `WOMPI_INTEGRITY_SECRET`: secreto de integridad para calcular la firma del checkout.
- `WOMPI_PRIVATE_KEY`: llave privada para consultar y verificar transacciones.
- `WOMPI_API_BASE=https://sandbox.wompi.co/v1`: API de pruebas de Wompi. Para producción, usa `https://production.wompi.co/v1`.
- `STORE_ADMIN_TOKEN`: token aleatorio largo para proteger las rutas de administración del catálogo.

No compartas ni subas llaves privadas, tokens ni el secreto de integridad al repositorio. Si una credencial se expone, revócala y genera otra.

## Catálogo propio: cargar un producto real

El catálogo propio comienza vacío intencionalmente: no se convierten los precios de ejemplo del armario en precios de venta. Primero confirma el precio en COP, la imagen, la talla y el inventario real.

Con una herramienta HTTP como Postman o curl, llama al endpoint protegido:

```bash
curl -X POST "https://TU-BACKEND.onrender.com/api/tienda/admin/productos" \
  -H "Content-Type: application/json" \
  -H "X-Store-Admin-Token: TU_STORE_ADMIN_TOKEN" \
  -d '{
    "nombre": "Camiseta de prueba",
    "descripcion": "Producto de prueba; reemplázalo antes de vender",
    "categoria": "camiseta",
    "color": "Azul",
    "talla": "M",
    "precio": 50000,
    "url_imagen": "https://URL-HTTPS-DE-LA-IMAGEN",
    "stock": 5
  }'
```

Los valores anteriores son un ejemplo de formato, no un producto ni precio recomendado. El precio debe ser el que realmente vas a cobrar. El endpoint responde con `id_producto` cuando se crea correctamente.

Para ajustar inventario, precio o disponibilidad:

```bash
curl -X PATCH "https://TU-BACKEND.onrender.com/api/tienda/admin/productos/ID_PRODUCTO" \
  -H "Content-Type: application/json" \
  -H "X-Store-Admin-Token: TU_STORE_ADMIN_TOKEN" \
  -d '{"stock": 8, "precio": 55000, "activo": true}'
```

## Webhooks de pago

- Mercado Pago: registra en el panel de desarrolladores la URL de `MP_NOTIFICATION_URL`.
- Wompi: registra `https://TU-BACKEND.onrender.com/api/tienda/webhooks/wompi` como URL de eventos de transacción en el dashboard de Wompi.

Los webhooks no confían en el estado enviado por el navegador: el backend consulta la transacción directamente con la API del proveedor y compara referencia, moneda y monto. La tienda reserva inventario al iniciar el checkout y lo libera si el proveedor confirma rechazo o cancelación.

## Tiendas externas

- Mercado Libre: el backend usa la búsqueda pública de artículos de Mercado Libre Colombia y redirige al permalink del vendedor. La disponibilidad puede cambiar en el sitio de origen.
- Amazon, SHEIN y Temu: por ahora se muestran enlaces a sus sitios oficiales, no un catálogo inventado. Para mostrar sus productos dentro de FitAI se requiere acceso autorizado a sus herramientas/API o enlaces de afiliado válidos para la cuenta y región. Amazon indica que su Creators API requiere registrarse como Amazon Associate y solicitar acceso: https://affiliate-program.amazon.com/creatorsapi/docs/en-us/onboarding. SHEIN ofrece un programa oficial de afiliados: https://www.shein.com.co/affiliate-a-427.html. Temu ofrece un programa de afiliados y una plataforma de partners con APIs sujetas a registro/autorización: https://www.temu.com/co-en/affiliate_recruit.html y https://partner-us.temu.com/.

## Endpoints

- `GET /api/tienda/productos?q=camisa&origen=todos`
- `GET /api/tienda/marketplaces`
- `POST /api/tienda/checkout` (JWT de usuario obligatorio)
- `GET /api/tienda/pedidos` (JWT de usuario obligatorio)
- `GET /api/tienda/pedidos/<referencia>/verificar` (JWT de usuario obligatorio)
- `POST /api/tienda/admin/productos` (token de administración)
- `PATCH /api/tienda/admin/productos/<id>` (token de administración)

## Lista de pruebas antes de producción

1. En modo sandbox, agregar producto y confirmar que el precio y el inventario aparecen correctamente.
2. Probar sin iniciar sesión: el checkout debe detenerse.
3. Probar carrito manipulado con ID inexistente, cantidad negativa y precio alterado: el servidor no debe aceptar precios del cliente.
4. Completar un pago de prueba aprobado y confirmar que el estado solo pasa a `pagado` tras verificación del proveedor.
5. Probar rechazo/cancelación y comprobar que el inventario se libera una sola vez.
6. Repetir notificaciones del webhook y comprobar que no duplican cobros ni liberaciones de stock.
7. Configurar avisos de pedido, política de privacidad, envíos, devoluciones, impuestos y soporte antes de vender de verdad.
