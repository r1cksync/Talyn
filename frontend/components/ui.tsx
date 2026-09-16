'use client';
import * as Dialog from '@radix-ui/react-dialog';
import { X, LoaderCircle, ArrowUpRight, AudioLines } from 'lucide-react';
import type { ReactNode, ButtonHTMLAttributes } from 'react';

export function Brand({ light = false }: { light?: boolean }) { return <a href="/" className={'brand ' + (light ? 'brand-light' : '')} aria-label="Talyn home"><span className="brand-mark"><AudioLines size={22} strokeWidth={2.5}/></span>talyn<span className="brand-dot">.</span></a>; }
export function Button({ children, variant = 'primary', busy, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: string; busy?: boolean }) { return <button {...props} disabled={props.disabled || busy} className={`button ${variant} ${props.className || ''}`}>{busy && <LoaderCircle size={16} className="spin"/>}{children}</button>; }
export function Badge({ children, tone = '' }: { children: ReactNode; tone?: string }) { return <span className={'badge ' + tone}>{children}</span>; }
export function Modal({ title, description, open, onOpenChange, children }: { title: string; description?: string; open: boolean; onOpenChange: (v: boolean) => void; children: ReactNode }) {
  return <Dialog.Root open={open} onOpenChange={onOpenChange}><Dialog.Portal><Dialog.Overlay className="modal-overlay"/><Dialog.Content className="modal"><div className="modal-head"><div><Dialog.Title>{title}</Dialog.Title><Dialog.Description>{description || 'Complete the fields below.'}</Dialog.Description></div><Dialog.Close className="icon-button" aria-label="Close dialog"><X size={20}/></Dialog.Close></div>{children}</Dialog.Content></Dialog.Portal></Dialog.Root>;
}
export function Empty({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) { return <div className="empty"><span className="empty-icon"><ArrowUpRight size={28}/></span><h3>{title}</h3><p>{children}</p>{action}</div>; }
export function Loading() { return <div className="loading" role="status"><LoaderCircle className="spin" size={22}/> Loading your workspace…</div>; }
export function ErrorNotice({ message, onClose }: { message: string; onClose?: () => void }) { return <div className="notice error" role="alert"><span>{message}</span>{onClose && <button onClick={onClose} aria-label="Dismiss message"><X size={17}/></button>}</div>; }
