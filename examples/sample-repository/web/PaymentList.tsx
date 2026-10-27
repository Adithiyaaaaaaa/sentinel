type Payment = {
  id: string;
  description: string;
  amountCents: number;
  status: "settled" | "pending";
};

export function PaymentList({ payments }: { payments: Payment[] }) {
  return (
    <section aria-label="Payments">
      {payments.map((payment) => (
        <article key={payment.id}>
          <strong>{payment.description}</strong>
          <span>{(payment.amountCents / 100).toFixed(2)}</span>
          <small>{payment.status}</small>
        </article>
      ))}
    </section>
  );
}
