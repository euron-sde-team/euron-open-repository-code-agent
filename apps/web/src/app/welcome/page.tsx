"use client";

import { FolderGit2, Users } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { AuthLayout } from "@/components/auth/auth-layout";
import { MIN_PASSWORD_LENGTH } from "@/components/shell/password-form";
import { Button } from "@/components/ui/button";
import { ErrorNotice, Spinner } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/input";
import { useSignup, useSystemInfo } from "@/lib/queries";
import { runtimeEnv } from "@/lib/runtime-env";

/**
 * First-run setup: the first account becomes the administrator of the deployment and gets an
 * organisation with a first project. Where sign-up is open, the same page creates later
 * accounts; where it is closed, it sends people to sign in.
 */
function WelcomeForm() {
  const router = useRouter();
  const system = useSystemInfo();
  const signup = useSignup({ silent: true });
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const setup = system.data?.needs_setup ?? false;

  useEffect(() => {
    // Once this form has created the account, setup is over and sign-up may be closed: the
    // answer that says so must not send the new administrator to the sign-in page.
    if (signup.isSuccess) return;
    if (system.data && !system.data.needs_setup && !system.data.allow_signup) {
      router.replace("/login");
    }
  }, [signup.isSuccess, system.data, router]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await signup.mutateAsync({
        name,
        email,
        password,
      });
      router.replace("/");
    } catch {
      // The error is rendered from the mutation state.
    }
  }

  if (!system.data) {
    return (
      <div className="flex justify-center" role="status" aria-label="Loading">
        <Spinner className="size-5" />
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="w-full space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {setup ? `Set up ${system.data.product_name}` : "Create your account"}
        </h1>
        <p className="text-muted-foreground mt-1.5 text-[13.5px]">
          {setup
            ? "Create the first account. It becomes the administrator of this deployment."
            : "You can create a workspace next, connect a repository and invite your team."}
        </p>
      </div>
      <Field label="Your name" htmlFor="name">
        <Input
          id="name"
          name="name"
          autoComplete="name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          required
          autoFocus
        />
      </Field>
      <Field label="Email" htmlFor="email">
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
      </Field>
      <Field label="Password" htmlFor="password" hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="new-password"
          value={password}
          minLength={MIN_PASSWORD_LENGTH}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
      </Field>
      <ul className="text-muted-foreground space-y-1.5 text-[12.5px]">
        <li className="flex items-center gap-2">
          <FolderGit2 className="text-subtle size-3.5" aria-hidden /> Connect repositories once you are in
        </li>
        <li className="flex items-center gap-2">
          <Users className="text-subtle size-3.5" aria-hidden /> Create a workspace and invite your team
        </li>
      </ul>
      {signup.error ? <ErrorNotice message={signup.error.message} /> : null}
      <Button type="submit" size="lg" className="w-full" loading={signup.isPending}>
        {setup ? "Create the administrator account" : "Create account"}
      </Button>
      {!setup ? (
        <p className="text-muted-foreground text-center text-[13px]">
          Already have an account?{" "}
          <Link href="/login" className="text-primary font-medium hover:underline">
            Sign in
          </Link>
        </p>
      ) : null}
    </form>
  );
}

export default function WelcomePage() {
  return (
    <AuthLayout productName={runtimeEnv().productName}>
      <WelcomeForm />
    </AuthLayout>
  );
}
