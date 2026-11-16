import csv
import argparse
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, List, Optional


def parse_date(val: str) -> Optional[date]:
    return date.fromisoformat(val.strip()) if val and val.strip() else None


def parse_money(val: str) -> Decimal:
    return Decimal(val.strip()).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def generate_report(data_dir: Path, report_date: date) -> str:
    contracts = {}
    with open(data_dir / "contracts.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            contracts[row["contract_id"]] = {
                "contract_id": row["contract_id"],
                "contractor": row["contractor"],
                "amount": parse_money(row["amount"]),
                "signed_at": parse_date(row["signed_at"]),
            }

    works_by_contract: Dict[str, List[dict]] = {cid: [] for cid in contracts}
    works_map: Dict[str, dict] = {}
    with open(data_dir / "works.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            completed_at = parse_date(row["completed_at"])
            cancelled_at = parse_date(row["cancelled_at"])

            if cancelled_at and cancelled_at <= report_date:
                status_on_date = "cancelled"
            elif completed_at and completed_at <= report_date:
                status_on_date = "done"
            else:
                status_on_date = "planned"

            work = {
                "work_id": row["work_id"],
                "contract_id": row["contract_id"],
                "title": row["title"],
                "price": parse_money(row["price"]),
                "status": status_on_date,
                "completed_at": completed_at,
                "cancelled_at": cancelled_at,
                "paid": Decimal("0.00"),
                "remaining": Decimal("0.00"),
            }
            works_by_contract[row["contract_id"]].append(work)
            works_map[row["work_id"]] = work

    unallocated_pool: Dict[str, Decimal] = {cid: Decimal("0.00") for cid in contracts}
    queued_pool: Dict[str, Decimal] = {cid: Decimal("0.00") for cid in contracts}

    with open(data_dir / "payments.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid = row["contract_id"]
            wid = row["work_id"].strip()
            amount = parse_money(row["amount"])
            status = row["status"].strip()
            created_at = parse_date(row["created_at"])
            paid_at = parse_date(row["paid_at"])
            refunded_at = parse_date(row["refunded_at"])

            if status == "queued" and created_at and created_at <= report_date:
                queued_pool[cid] += amount
                continue

            if paid_at and paid_at <= report_date:
                if status == "refunded" and refunded_at and refunded_at <= report_date:
                    continue

                if wid and wid in works_map:
                    works_map[wid]["paid"] += amount
                else:
                    unallocated_pool[cid] += amount

    lines = [f"ОТЧЁТ ПО ВЗАИМОРАСЧЁТАМ С ПОДРЯДЧИКАМИ НА {report_date.isoformat()}", "=" * 80]

    for cid, contract in contracts.items():
        works = works_by_contract[cid]
        pool = unallocated_pool[cid]

        done_works = sorted(
            [w for w in works if w["status"] == "done"],
            key=lambda x: (x["completed_at"], x["work_id"]),
        )
        planned_works = sorted(
            [w for w in works if w["status"] == "planned"],
            key=lambda x: x["work_id"],
        )

        for w in done_works + planned_works:
            if pool <= Decimal("0.00"):
                break
            need = max(Decimal("0.00"), w["price"] - w["paid"])
            allocated = min(pool, need)
            w["paid"] += allocated
            pool -= allocated

        total_active_price = Decimal("0.00")
        total_paid = Decimal("0.00")
        total_remaining = Decimal("0.00")

        lines.append(f"\nДоговор {cid}: {contract['contractor']} (Сумма договора: {contract['amount']} ₽)")
        lines.append("-" * 80)
        lines.append(f"{'ID':<6} | {'Работа':<28} | {'Статус':<10} | {'Цена':>10} | {'Оплачено':>10} | {'Остаток':>10}")
        lines.append("-" * 80)

        for w in works:
            if w["status"] == "cancelled":
                effective_price = Decimal("0.00")
                w["remaining"] = Decimal("0.00")
            else:
                effective_price = w["price"]
                w["remaining"] = max(Decimal("0.00"), effective_price - w["paid"])

            total_active_price += effective_price
            total_paid += w["paid"]
            total_remaining += w["remaining"]

            status_ru = {"done": "принята", "planned": "в плане", "cancelled": "отменена"}[w["status"]]
            lines.append(
                f"{w['work_id']:<6} | {w['title']:<28} | {status_ru:<10} | "
                f"{w['price']:>10} | {w['paid']:>10} | {w['remaining']:>10}"
            )

        lines.append("-" * 80)
        lines.append(
            f"{'ИТОГО ПО ДЕЙСТВУЮЩИМ РАБОТАМ:':<49} | "
            f"{total_active_price:>10} | {total_paid:>10} | {total_remaining:>10}"
        )
        if pool > Decimal("0.00"):
            lines.append(f"  [!] Переплата / нераспределённый остаток аванса по договору: {pool} ₽")
        if queued_pool[cid] > Decimal("0.00"):
            lines.append(f"  [i] Справочно: в очереди на оплату (не списано со счёта): {queued_pool[cid]} ₽")

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Отчёт по оплатам работ по договорам.")
    parser.add_argument("--data", type=Path, default=Path("data"), help="Путь к папке с CSV")
    parser.add_argument("--date", type=str, default="2026-11-10", help="Дата отчёта (YYYY-MM-DD)")
    args = parser.parse_args()

    print(generate_report(args.data, date.fromisoformat(args.date)))
