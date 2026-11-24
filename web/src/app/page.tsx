import { redirect } from "next/navigation";

// D-01 replaces this with "signed in? go home (homePathFor), else /login".
export default function Index() {
  redirect("/login");
}
