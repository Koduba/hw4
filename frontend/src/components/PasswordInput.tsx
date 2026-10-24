import { useState, type InputHTMLAttributes } from 'react'

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & { id: string }

/** Password field with a show/hide toggle. */
export default function PasswordInput(props: Props) {
  const [visible, setVisible] = useState(false)
  return (
    <div className="password-field">
      <input {...props} type={visible ? 'text' : 'password'} spellCheck={false} />
      <button
        type="button"
        className="password-field__toggle"
        aria-controls={props.id}
        aria-pressed={visible}
        onClick={() => setVisible((v) => !v)}
      >
        {visible ? 'Hide' : 'Show'}
      </button>
    </div>
  )
}
