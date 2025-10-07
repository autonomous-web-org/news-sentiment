import { NSSHeader, NSSMain } from '../../_components/home';

export default function NSSContainer() {
  return (
    <div className="bg-background-light dark:bg-background-dark font-display text-black dark:text-white min-h-screen flex flex-col">
      <NSSHeader />
      <NSSMain />
    </div>
  );
}
