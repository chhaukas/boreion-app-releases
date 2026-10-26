# Produktstatus — sentral Boreion-publisering

2026-10-26: Sentral scan, godkjent artifact-overføring, proveniens/signatur/hash-verifikasjon i Docker-sandkasse og separat atomisk release-writer er implementert på kodegren. Reader-App brukes kun sentralt med Actions-read; private Android-prosjekter trenger ingen publiseringshemmeligheter. Portalens eksisterende releaseformat bevares. Ingen database eller server kreves.

Unit-/negative tester, actionlint og en ekte midlertidig signert lokal APK i den faktiske Docker-sandkassen er verifisert. CI kjører uten App-secrets og tester ekte lokal signatur med slettbare fixtures. Ingen produksjonsreleases er publisert, ingen produksjonshemmeligheter er opprettet eller flyttet.

Ikke produksjonsaktivert: Koden må gjennomgås/merges til beskyttet main. Eieren må konfigurere reader-App/installasjon, sentral App-ID/PEM og lukket kildepolicy samt production-/beta-environments. Se README for eksakte steg og GitHub Personal-begrensninger. Reell App-autentisering, private artifacts og GitHub-godkjenning er ikke ende-til-ende-verifisert uten dette oppsettet. Tom policy avviser alle kilder. Hver produksjonsutgivelse krever review; første krever også eksplisitt policy-godkjenning. Ingen merge til main eller live dispatch er utført av denne leveransen.
