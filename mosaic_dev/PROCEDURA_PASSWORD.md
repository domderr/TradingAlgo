# Procedura aggiornamento password

Questa procedura aggiorna gli accessi dell'area riservata del sito senza pubblicare password in chiaro.

## File coinvolti

- Sorgente locale: `mosaic_dev/Subscriptions.xlsx`
- Output pubblicato: `assets/subscriptions.json`
- Script: `mosaic_dev/update_subscriptions.py`

## Aggiornare un accesso

1. Aprire `Subscriptions.xlsx`.
2. Aggiornare o aggiungere una riga con:
   - `nome`: nome mostrato dopo il login.
   - `password`: nuova password in chiaro, solo nel file Excel locale.
   - `markets`: mercati abilitati, separati da virgola. Usare `All` per tutti.
   - `status`: lasciare vuoto per accesso attivo; usare `inactive` per disattivarlo.
3. Salvare e chiudere Excel.
4. Eseguire da `mosaic_dev`:

```powershell
python update_subscriptions.py
```

5. Verificare `assets/subscriptions.json`: deve contenere solo `password_hash`, mai password in chiaro.
6. Testare l'accesso in locale o sul sito aggiornato.
7. Commit/push solo quando richiesto esplicitamente.

## Note operative

- Lo script calcola hash SHA-256 compatibili con `reserved-area.html`.
- `Italy` e `Italia` vengono normalizzati in `Italy30`.
- Una riga con `status` vuoto e' considerata attiva.
- Valori `inactive`, `disabled`, `no`, `false`, `0`, `off`, `revoked` disattivano l'accesso.
